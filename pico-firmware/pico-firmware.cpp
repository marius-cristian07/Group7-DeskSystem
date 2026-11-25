// Edited by : Edris Fiazi
// Edited on : 19.11.2026
// Purpose   : KAN-30 Flash the red LED and sound the buzzer before movement, and cancel when the button is pressed.

#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "wifi_credentials.h"
#include "lwip/apps/http_client.h"
#include <atomic>
#include <string>

enum class HealthResult
{
    pending,
    unavailable,
    available
};

static std::atomic<HealthResult> health_result{HealthResult::unavailable};

static err_t discard_health_body(void *, altcp_pcb *connection,
                                 pbuf *body, err_t error)
{
    if (body != nullptr)
    {
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
    if (!ipaddr_aton(BACKEND_IP, &address))
    {
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

    if (result != ERR_OK)
    {
        printf("Could not start health check (%d)\n", static_cast<int>(result));
        health_result.store(HealthResult::unavailable);
    }
}

constexpr uint LED_RED = 7;
constexpr uint BUTTON = 10;
constexpr uint BUZZER = 20;
constexpr int BLINKPHASE_MS = 250;

static std::string movementId;
static bool warningActive = false;
static volatile bool buttonPressed = false;
static absolute_time_t warningStarted;
static absolute_time_t usbTimeout;

void warnsignalSet(bool on)
{
    gpio_put(LED_RED, on);
    gpio_put(BUZZER, on);
}

void buttonPressedCallback(uint, uint32_t)
{
    buttonPressed = true; // Remember a short press between two USB messages.
}

void warningInit()
{
    gpio_init(LED_RED);
    gpio_set_dir(LED_RED, GPIO_OUT);
    gpio_init(BUZZER);
    gpio_set_dir(BUZZER, GPIO_OUT);
    warnsignalSet(false);

    gpio_init(BUTTON);
    gpio_set_dir(BUTTON, GPIO_IN);
    // The carrier board button is expected to drive GP10 high when pressed.
    gpio_pull_down(BUTTON);
    gpio_set_irq_enabled_with_callback(BUTTON, GPIO_IRQ_EDGE_RISE, true, buttonPressedCallback);
}

void stopWarning()
{
    warningActive = false;
    warnsignalSet(false);
}

void handleWarningCommand(const std::string &line)
{
    if (line == "STOP")
    {
        stopWarning();
        movementId.clear();
        printf("IDLE\n");
        return;
    }

    // Each command belongs to one movement, e.g. START followed by its ID.
    const auto space = line.find(' ');
    if (space == std::string::npos)
        return;
    const std::string command = line.substr(0, space);
    const std::string id = line.substr(space + 1);
    if (id.size() != 32)
        return;

    if (command == "START" && movementId.empty())
    {
        movementId = id;
        buttonPressed = false;
        warningStarted = get_absolute_time();
        warningActive = true;
        warnsignalSet(!buttonPressed && !gpio_get(BUTTON));
    }
    if (id != movementId)
    {
        printf("UNKNOWN %s\n", id.c_str());
        return;
    }

    usbTimeout = make_timeout_time_ms(2000);
    if (buttonPressed || gpio_get(BUTTON))
    {
        buttonPressed = true;
        stopWarning();
        printf("CANCEL %s\n", id.c_str());
    }
    else if (warningActive && command == "FINISH")
    {
        stopWarning();
        const bool cancelled = buttonPressed || gpio_get(BUTTON);
        printf("%s %s\n", cancelled ? "CANCEL" : "CLEAR", id.c_str());
    }
    else if (warningActive && (command == "POLL" || command == "START"))
    {
        printf("ACTIVE %s\n", id.c_str());
    }
    else
    {
        printf("UNKNOWN %s\n", id.c_str());
    }
}

void updateWarning()
{
    if (warningActive)
    {
        if (buttonPressed || time_reached(usbTimeout))
        {
            buttonPressed = true;
            stopWarning();
        }
        else
        {
            const int64_t elapsedMs = absolute_time_diff_us(warningStarted, get_absolute_time()) / 1000;
            warnsignalSet((elapsedMs / BLINKPHASE_MS) % 2 == 0);
        }
    }

    static std::string line;
    int ch;
    while ((ch = getchar_timeout_us(0)) >= 0)
    {
        if (ch == '\n')
        {
            if (line.size() < 64)
                handleWarningCommand(line);
            line.clear();
        }
        else if (ch != '\r' && line.size() < 64)
        {
            line += static_cast<char>(ch);
        }
    }
}

int main()
{
    stdio_init_all();
    warningInit();
    const bool wifi_ready = cyw43_arch_init() == 0;
    if (wifi_ready)
    {
        cyw43_arch_enable_sta_mode();
        cyw43_arch_wifi_connect_async(WIFI_SSID, WIFI_PASSWORD, CYW43_AUTH_WPA2_AES_PSK);
    }

    bool backend_available = false;
    bool led_on = false;
    absolute_time_t next_check = get_absolute_time();
    absolute_time_t next_led = get_absolute_time();
    while (true)
    {
        updateWarning();
        if (wifi_ready && time_reached(next_led))
        {
            const auto status = health_result.load();
            if (status != HealthResult::pending)
            {
                backend_available = status == HealthResult::available;
                if (time_reached(next_check))
                {
                    check_backend();
                    next_check = make_timeout_time_ms(5000);
                }
            }
            led_on = backend_available || !led_on;
            cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, led_on);
            next_led = make_timeout_time_ms(500);
        }
        sleep_ms(2);
    }
}
