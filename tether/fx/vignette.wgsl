//! blend = "alpha"
//!
//! [[param]]
//! name = "strength"
//! default = 0.5

// The view's edges darken and take the beam's colour while the craft holds a lock.
fn mod_fragment(input: ModInput) -> vec4<f32> {
    let centred = input.uv * 2.0 - vec2<f32>(1.0);
    let edge = smoothstep(0.55, 1.35, length(centred));
    return vec4<f32>(input.colour.rgb * 0.5, edge * param_strength());
}
