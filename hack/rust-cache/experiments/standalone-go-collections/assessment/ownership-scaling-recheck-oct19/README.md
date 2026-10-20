# Ownership reuse: representative-scale verification reopened

The earlier full dagger/dagger listing improved 68.37 → 56.81 seconds, with lower CPU and allocation. A reliable complete-command gain of that size can justify this patch even when a small fixture gains little. The earlier standalone screen had 16 packages; the real listing had about 800 packages across 80 modules. Treating that screen alone as grounds to reject the patch understated its possible value.

The next comparison uses the existing current-main port, on Go main 334136faaa, with eight modules and eight packages in each. Both versions are installed in one fixed workspace. The driver includes a same-code control and a one-package control. Each measured pair renames a test; each invocation edits source, starts a fresh CLI, verifies ordered rows and includes successful cleanup. Telemetry and normal cache behavior stay enabled.

Only three warmup commands completed in this attempt. Host CPU pressure during those commands was 51–60%. The driver was stopped between commands to investigate the supplied CI trace. Sources were restored. There are no measured pairs and no new verified speed claim. The source patch, raw warmups and interrupted attempt are retained for the next run. No ownership PR is open yet.
