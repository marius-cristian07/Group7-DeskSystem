from dataclasses import dataclass


@dataclass(frozen=True)
class DeskHealth:
    classification: str
    faults: tuple = ()

    @property
    def blocks_movement(self):
        return self.classification != "healthy"


def classify_faults(state):
    # a missing reading says nothing about the mechanical condition
    if state is None:
        return DeskHealth("unavailable")

    flags = {
        "isAntiCollision": "collision",
        "isPositionLost": "position_lost",
        "isOverloadProtectionUp": "overload_up",
        "isOverloadProtectionDown": "overload_down",
    }
    faults = [name for flag, name in flags.items() if state.get(flag) is True]
    status = str(state.get("status", "")).strip().lower()
    uncertain = status in ("", "unknown", "unavailable", "offline", "unreachable")
    if status != "normal" and not uncertain:
        faults.append("status_fault")
    if faults:
        return DeskHealth("faulty", tuple(faults))
    if uncertain:
        return DeskHealth("unknown")
    return DeskHealth("healthy")


def movement_outcome(state, target_mm, tolerance_mm=2):
    # being at the target never clears a fault in the same reading
    health = classify_faults(state)
    if health.classification == "faulty":
        return "desk_error"
    if health.blocks_movement:
        return "unverified"
    if abs(state["position_mm"] - target_mm) <= tolerance_mm and state["speed_mms"] == 0:
        return "reached"
    return "moving"
