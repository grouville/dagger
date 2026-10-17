from pathlib import Path
import difflib,hashlib,json,shutil
root=Path(__file__).parent
before=Path('/tmp/rust-cache-sipsma-review/dang-module-blueprint-content-key')
after=Path('/tmp/dang-direct-builtin-receivers')
shutil.copytree(before,after,ignore=shutil.ignore_patterns('.git','node_modules','__pycache__','*.test'))
(root/'baseline-identity.json').write_text(json.dumps(dict(path=str(before),files={name:hashlib.sha256((before/name).read_bytes()).hexdigest() for name in ['pkg/dang/eval.go','pkg/dang/ast_expressions.go','pkg/dang/builtins.go','go.mod','go.sum']}),indent=2)+'\n')
source=(before/'pkg/dang/eval.go').read_text()
start=source.index('\t\t\tbuiltinFn := BuiltinFunction{',source.index('// Register all builtin methods'))
end=source.index('\n\t\t\tmethodKey := ',start)
old=source[start:end]
new=old.replace('builtinFn := BuiltinFunction{','builtinFn := builtinMethod{\n\t\t\t\tBuiltinFunction: BuiltinFunction{',1)
new=new.replace('\t\t\t\tCallFn: func(ctx context.Context, scope ValueScope, args map[string]Value) (Value, error) {\n\t\t\t\t\tselfVal, _ := scope.Self()', '\t\t\t\t},\n\t\t\t\tcallReceiver: func(ctx context.Context, selfVal Value, args map[string]Value) (Value, error) {',1)
assert new!=old and 'scope.Self()' not in new
source=source[:start]+new+source[end:]
(after/'pkg/dang/eval.go').write_text(source)
source=(before/'pkg/dang/ast_expressions.go').read_text()
import re
pattern=r'if builtinFn, ok := method\.\(BuiltinFunction\); ok \{\n(?:\s*//[^\n]*\n)*\s*return BoundBuiltinMethod\{Method: builtinFn, Receiver: rec\}, nil\n\s*\}'
source,count=re.subn(pattern,'if bound, ok := bindBuiltinMethod(method, rec); ok {\n\t\t\t\t\t\treturn bound, nil\n\t\t\t\t\t}',source)
assert count==5,count
anchor='\t\tif fn, ok := funVal.(BuiltinFunction); ok && fn.Deprecated != "" {'
assert source.count(anchor)==1
source=source.replace(anchor,'\t\tfn, builtin := funVal.(BuiltinFunction)\n\t\tif method, ok := funVal.(builtinMethod); ok {\n\t\t\tfn, builtin = method.BuiltinFunction, true\n\t\t}\n\t\tif builtin && fn.Deprecated != "" {',1)
(after/'pkg/dang/ast_expressions.go').write_text(source)
(after/'pkg/dang/builtin_method.go').write_text('''package dang

import (
 "context"
 "fmt"
)

// Registered methods accept the receiver as a value, so binding them does not
// require an evaluation scope. BuiltinFunction supplies the callable metadata.
// Hand-written BuiltinFunction callbacks still receive their original scope.
type builtinMethod struct {
 BuiltinFunction
 callReceiver func(context.Context, Value, map[string]Value) (Value, error)
}

func (m builtinMethod) Call(ctx context.Context, scope ValueScope, args map[string]Value) (Value, error) {
 receiver, _ := scope.Self()
 return m.callReceiver(ctx, receiver, args)
}

type boundBuiltinMethod struct {
 builtinMethod
 receiver Value
}

func (m boundBuiltinMethod) Call(ctx context.Context, _ ValueScope, args map[string]Value) (Value, error) {
 return m.callReceiver(ctx, m.receiver, args)
}

func (m boundBuiltinMethod) String() string {
 return fmt.Sprintf("bound_builtin_method(%s)", m.builtinMethod.String())
}

func (boundBuiltinMethod) MarshalJSON() ([]byte, error) {
 return nil, fmt.Errorf("cannot marshal bound method value")
}

func bindBuiltinMethod(method, receiver Value) (Callable, bool) {
 switch method := method.(type) {
 case builtinMethod:
  return boundBuiltinMethod{builtinMethod: method, receiver: receiver}, true
 case BuiltinFunction:
  return BoundBuiltinMethod{Method: method, Receiver: receiver}, true
 default:
  return nil, false
 }
}
''')
print('Prepared isolated registered-method prototype; original module source untouched.')
