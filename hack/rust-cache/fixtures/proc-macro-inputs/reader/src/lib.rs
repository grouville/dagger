extern crate proc_macro;
use proc_macro::TokenStream;

#[proc_macro]
pub fn workspace_value(_input: TokenStream) -> TokenStream {
    let root = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    let override_path = root.join("../data/override.txt");
    let selected = if override_path.exists() {
        override_path
    } else {
        root.join("../data/value.txt")
    };
    let text = std::fs::read_to_string(selected).unwrap();
    format!("{}u32", text.trim()).parse().unwrap()
}
