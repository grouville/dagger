import { argument, check, Directory, func, object } from "@dagger.io/dagger";

@object()
export class CtorMarker {
  @func()
  source: Directory;

  constructor(
    @argument({ defaultPath: "/", ignore: [".git", "ignored.txt"] })
    source: Directory,
  ) {
    this.source = source;
  }

  @func()
  async read(): Promise<string> {
    return this.source.file("marker.txt").contents();
  }

  @func()
  @check()
  async verify(): Promise<void> {
    const value = await this.read();
    if (value !== "pass") {
      throw new Error(`marker mismatch: ${JSON.stringify(value)}`);
    }
  }
}
