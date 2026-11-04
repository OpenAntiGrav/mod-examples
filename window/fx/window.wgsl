//! blend = "alpha"

// A round window: the engine's view of the far road through `engine_uv`, which stays on the
// surface whether the view is drawn every frame or held as a snapshot. With no view for this
// craft (a second seat of a split, or the portal not ready) a ripple of the craft's colour.
fn mod_fragment(input: ModInput) -> vec4<f32> {
    let centred = input.uv * 2.0 - vec2<f32>(1.0);
    let radius = length(centred);
    let inside = 1.0 - smoothstep(0.96, 1.0, radius);
    if !engine_texture_bound() {
        let ripple = 0.5 + 0.5 * sin(radius * 24.0 - input.time * 6.0);
        return vec4<f32>(input.colour.rgb * (0.4 + 0.6 * ripple), inside);
    }
    let view = engine_texture(engine_uv(input.world)).rgb;
    let rim = smoothstep(0.88, 0.95, radius);
    return vec4<f32>(mix(view, input.colour.rgb, rim), inside);
}
