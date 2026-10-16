fn main() {
    assert_eq!(app::value(), 11);
    std::fs::write("../test-data/generated.txt", "from custom test").unwrap();
    println!("custom harness executed");
}
