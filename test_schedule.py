from app.planner.schedule_manager import ScheduleManager

planner = ScheduleManager()

planner.add_schedule(
    "2026-07-22",
    "06:00",
    "Wake up"
)

planner.add_schedule(
    "2026-07-22",
    "08:00",
    "LeetCode"
)

planner.add_schedule(
    "2026-07-22",
    "10:00",
    "Sophia Development"
)

print(
    planner.get_schedule("2026-07-22")
)