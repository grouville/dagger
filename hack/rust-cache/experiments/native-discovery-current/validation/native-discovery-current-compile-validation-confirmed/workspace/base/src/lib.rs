/// A value supplied to the other crate.
/// ```
/// assert_eq!(base::value(), 10);
/// ```
pub fn value() -> u32 { 10 }
#[cfg(test)] mod tests { #[test] fn expected_value() { assert_eq!(super::value(), 10); } }
