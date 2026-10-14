pub fn value() -> u32 {
    reader::workspace_value!()
}

#[test]
fn expected_value() {
    assert_eq!(value(), 10);
}
