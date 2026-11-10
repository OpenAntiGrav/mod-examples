//! blend = "alpha"
//!
//! [[param]]
//! name = "speed"
//! default = 2.0

// Three pulses running from the shooter to the target over a solid core, drawn over the picture: an added colour is lost on a pale road. No loops: the engine
// refuses them, so the sum is written out. `uv.x` runs along the beam, `uv.y` across it.
fn pulse(along: f32, phase: f32) -> f32 {
    let at = fract(along - phase);
    return smoothstep(0.0, 0.1, at) * smoothstep(0.35, 0.1, at);
}

fn mod_fragment(input: ModInput) -> vec4<f32> {
    let across = abs(input.uv.y * 2.0 - 1.0);
    let core = pow(1.0 - across, 3.0);
    let along = input.uv.x * 6.0;
    let clock = input.time * param_speed();
    let pulses = pulse(along, clock) + 0.5 * pulse(along * 0.5, clock * 0.7);
    let glow = smoothstep(0.0, 0.5, core) * (0.7 + pulses);
    let white = clamp(core * pulses * 2.0, 0.0, 1.0);
    return vec4<f32>(mix(input.colour.rgb * 0.7, vec3<f32>(1.0), white), min(glow, 1.0) * input.colour.a);
}
