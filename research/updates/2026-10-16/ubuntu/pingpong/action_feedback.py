"""Whitelist of public own-action execution feedback, never world state."""
FIELDS=('stroke','n_swing_steps_available','n_swing_steps','ik_residual',
        'blade_error_m','normal_error_deg','speed_scale','base','base_goal',
        'approach','table_contact_in_rehearsal','paddle_vel_delivered','T_from_now')
def public_feedback(info):
    return {key:info[key] for key in FIELDS if key in info}
