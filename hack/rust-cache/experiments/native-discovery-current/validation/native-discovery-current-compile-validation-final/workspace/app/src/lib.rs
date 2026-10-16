/// Verify filesystem changes made by an earlier Cargo test target.
/// ```
/// let manifest = std::env::var("CARGO_MANIFEST_DIR").unwrap();
/// let file = std::path::Path::new(&manifest).join("../test-data/generated.txt");
/// assert_eq!(std::fs::read_to_string(file).unwrap(), "from custom test");
/// ```
pub fn value() -> u32 { base::value() + 1 }
#[cfg(test)] mod tests {
    #[test] fn dependency_value() { assert_eq!(super::value(), 11); }
    #[test] fn runtime_workspace_input() {
        let text = std::fs::read_to_string("../test-data/value.txt").unwrap();
        assert_eq!(text.trim().parse::<u32>().unwrap(), base::value());
    }
}

pub fn edited_value() -> u64 { 44786563257266 }
