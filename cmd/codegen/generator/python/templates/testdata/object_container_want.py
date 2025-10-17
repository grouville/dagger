@typecheck
class Container(Type):

  def exec(self, args: list[str] | None, *, stdin: str | None = None) -> Container:
_args = [
  Arg("args", args),
  Arg("stdin", stdin),
]
    _ctx = self._select("exec", _args)
    return self.__class__(_ctx)