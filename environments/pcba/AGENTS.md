Read the repository AGENTS.md. This is a CPU-compatible MuJoCo prototype.
Keep scripted/oracle demonstrations explicitly separate from model-controlled runs.
Actor observations contain camera pixels, measured robot state and declared device
signals only. Exact board poses, latent test outcomes and scoring stay in diagnostics.
Vacuum attachment is an idealized proximity-gated weld, not a validated suction model.
Electrical tests are simulated device events, not SPICE or hardware measurements.
Do not label this prototype as a production robot controller or a validated VLA policy.
