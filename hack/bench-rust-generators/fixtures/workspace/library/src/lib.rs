pub fn message() -> &'static str {
    if cfg!(feature = "loud") {
        "HELLO FROM THE LIBRARY"
    } else {
        "hello from the library"
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn message_is_not_empty() {
        assert!(!super::message().is_empty());
    }
}
