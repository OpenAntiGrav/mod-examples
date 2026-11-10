//! blend = "alpha"

// A ring standing where the effect plays, turning, with a gap in it.
fn mod_fragment(input: ModInput) -> vec4<f32> {
    let centred = input.uv * 2.0 - vec2<f32>(1.0);
    let radius = length(centred);
    let band = smoothstep(0.62, 0.72, radius) * smoothstep(0.98, 0.86, radius);
    let angle = atan2(centred.y, centred.x) + input.time * 4.0;
    let gaps = smoothstep(-0.2, 0.2, sin(angle * 3.0));
    return vec4<f32>(input.colour.rgb, band * gaps * input.colour.a);
}
