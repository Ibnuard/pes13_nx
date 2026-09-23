# PERF33 result

No Switch hardware result is recorded yet. PERF32 diagnostics showed the throw-in clue: the host present call stayed short while busy translated PES workers returned when active play resumed. That supports testing a CPU translation policy, but it does not prove that all rendering work is CPU-side.

The acceptance test is a matched PERF33/control run at the same scene and clocks, with a log continuing for six minutes after kick-off and through a throw-in, replay and foul/goal transition.
