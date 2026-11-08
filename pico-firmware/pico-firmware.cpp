#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "wifi_credentials.h"
#include "lwip/apps/http_client.h"
#include <atomic>

enum class HealthResult { pending, unavailable, available };

static std::atomic<HealthResult> health_result{HealthResult::unavailable};

static err_t discard_health_body(void *, altcp_pcb *connection,
                                 pbuf *body, err_t error)
{
    if (body != nullptr) {
        altcp_recved(connection, body->tot_len);
        pbuf_free(body);
    }
    return error;
}

static void save_health_result(void *, httpc_result_t result,
                               u32_t, u32_t http_status, err_t)
{
    const bool ok = result == HTTPC_RESULT_OK && http_status == 200;
    health_result.store(ok ? HealthResult::available
                           : HealthResult::unavailable);
}

static void check_backend()
{
    ip_addr_t address;
    if (!ipaddr_aton(BACKEND_IP, &address)) {
        printf("Invalid backend IP address\n");
        health_result.store(HealthResult::unavailable);
        return;
    }

    static httpc_connection_t settings{};
    settings.result_fn = save_health_result;

    health_result.store(HealthResult::pending);
    cyw43_arch_lwip_begin();
    err_t result = httpc_get_file(&address, 8085, "/api/health",
                                  &settings, discard_health_body, nullptr, nullptr);
    cyw43_arch_lwip_end();

    if (result != ERR_OK) {
        printf("Could not start health check (%d)\n", static_cast<int>(result));
        health_result.store(HealthResult::unavailable);
    }
}


int main()
{
    stdio_init_all();

    // Initialise the Wi-Fi chip
    if (cyw43_arch_init()) {
        printf("Wi-Fi init failed\n");
        return -1;
    }

    cyw43_arch_enable_sta_mode();
    printf("Connecting to Wi-Fi...\n");

    int result = cyw43_arch_wifi_connect_timeout_ms(
        WIFI_SSID, WIFI_PASSWORD, CYW43_AUTH_WPA2_AES_PSK, 30000
    );

    if (result == 0) {
        printf("Connected to Wi-Fi\n");
    } else {
        printf("Wi-Fi connection failed (%d)\n", result);
    }

    // Update the LED using the latest completed health check
        bool backend_available = false;
    bool led_on = false;
    absolute_time_t next_check = get_absolute_time();

    while (true) {
        const HealthResult status = health_result.load();

        if (status != HealthResult::pending) {
            backend_available = status == HealthResult::available;

            if (time_reached(next_check)) {
                check_backend();
                next_check = make_timeout_time_ms(5000);
            }
        }

        led_on = backend_available || !led_on;
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, led_on);
        sleep_ms(500);
    }
}
