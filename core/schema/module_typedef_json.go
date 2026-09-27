package schema

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
)

// currentTypeDefsJSON projects the same metadata selected by the CLI's
// typedefs.graphql query. It preserves the ordinary schema-scoped TypeDef
// selection and its semantic adapters, but does not publish every returned
// field as an independent DagQL result. No cache exists outside DagQL.
func (s *moduleSchema) currentTypeDefsJSON(ctx context.Context, _ *core.Query, args currentTypeDefsArgs) (core.JSON, error) {
	dag, err := core.CurrentDagqlServer(ctx)
	if err != nil {
		return nil, err
	}
	var defs dagql.ObjectResultArray[*core.TypeDef]
	err = dag.Select(ctx, dag.Root(), &defs, dagql.Selector{
		Field: "currentTypeDefs", View: dag.View,
		Args: []dagql.NamedInput{
			{Name: "returnAllTypes", Value: dagql.Boolean(args.ReturnAllTypes)},
			{Name: "hideCore", Value: args.HideCore},
		},
	})
	if err != nil {
		return nil, err
	}
	return s.projectCLITypeDefs(ctx, defs)
}

func cliTypeRef(ref dagql.ObjectResult[*core.TypeDef]) (map[string]any, error) {
	t := ref.Self()
	if t == nil {
		return nil, fmt.Errorf("nil type reference in CLI metadata")
	}
	return map[string]any{"name": t.Name, "optional": t.Optional}, nil
}

func (s *moduleSchema) cliFunction(ctx context.Context, fn *core.Function) (map[string]any, error) {
	if fn == nil {
		return nil, nil
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	// This adapter preserves the authored check return type in legacy views.
	returned, err := s.functionReturnType(ctx, fn, struct{}{})
	if err != nil {
		return nil, err
	}
	ref, err := cliTypeRef(returned)
	if err != nil {
		return nil, err
	}
	args := make([]map[string]any, 0, len(fn.Args))
	for _, value := range fn.Args {
		arg := value.Self()
		if arg == nil {
			return nil, fmt.Errorf("nil function argument in CLI metadata")
		}
		argRef, err := cliTypeRef(arg.TypeDef)
		if err != nil {
			return nil, err
		}
		ignore := make([]string, len(arg.Ignore))
		copy(ignore, arg.Ignore)
		args = append(args, map[string]any{
			"name": arg.Name, "description": arg.Description, "defaultValue": arg.DefaultValue,
			"defaultPath": arg.DefaultPath, "ignore": ignore, "typeDef": argRef,
		})
	}
	return map[string]any{"name": fn.Name, "description": fn.Description,
		"sourceModuleName": fn.SourceModuleName, "returnType": ref, "args": args}, nil
}

func (s *moduleSchema) cliFunctions(ctx context.Context, functions dagql.ObjectResultArray[*core.Function]) ([]map[string]any, error) {
	result := make([]map[string]any, 0, len(functions))
	for _, fn := range functions {
		projected, err := s.cliFunction(ctx, fn.Self())
		if err != nil {
			return nil, err
		}
		if projected == nil {
			return nil, fmt.Errorf("nil function in CLI metadata")
		}
		result = append(result, projected)
	}
	return result, nil
}

func cliFields(fields dagql.ObjectResultArray[*core.FieldTypeDef]) ([]map[string]any, error) {
	result := make([]map[string]any, 0, len(fields))
	for _, value := range fields {
		field := value.Self()
		if field == nil {
			return nil, fmt.Errorf("nil field in CLI metadata")
		}
		ref, err := cliTypeRef(field.TypeDef)
		if err != nil {
			return nil, err
		}
		result = append(result, map[string]any{"name": field.Name, "description": field.Description, "typeDef": ref})
	}
	return result, nil
}

func (s *moduleSchema) projectCLITypeDefs(ctx context.Context, defs dagql.ObjectResultArray[*core.TypeDef]) (core.JSON, error) {
	rows := make([]map[string]any, 0, len(defs))
	for _, value := range defs {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		t := value.Self()
		if t == nil {
			return nil, fmt.Errorf("nil TypeDef in CLI metadata")
		}
		row := map[string]any{"name": t.Name, "kind": t.Kind, "optional": t.Optional,
			"asObject": nil, "asInterface": nil, "asScalar": nil, "asEnum": nil, "asInput": nil, "asList": nil}
		// Collections deliberately project their public get/subset/keys/list/
		// batch surface. Serializing the stored object directly is incorrect.
		object, err := s.typeDefAsObject(ctx, t, struct{}{})
		if err != nil {
			return nil, err
		}
		if object.Valid && object.Value.Self() != nil {
			obj := object.Value.Self()
			functions, err := s.cliFunctions(ctx, obj.Functions)
			if err != nil {
				return nil, err
			}
			fields, err := cliFields(obj.Fields)
			if err != nil {
				return nil, err
			}
			var constructor map[string]any
			if obj.Constructor.Valid {
				constructor, err = s.cliFunction(ctx, obj.Constructor.Value.Self())
				if err != nil {
					return nil, err
				}
			}
			row["asObject"] = map[string]any{"name": obj.Name, "description": obj.Description,
				"sourceModuleName": obj.SourceModuleName, "functions": functions, "fields": fields, "constructor": constructor}
		}
		if t.AsInterface.Valid && t.AsInterface.Value.Self() != nil {
			iface := t.AsInterface.Value.Self()
			functions, err := s.cliFunctions(ctx, iface.Functions)
			if err != nil {
				return nil, err
			}
			row["asInterface"] = map[string]any{"name": iface.Name, "description": iface.Description,
				"sourceModuleName": iface.SourceModuleName, "functions": functions}
		}
		if t.AsScalar.Valid && t.AsScalar.Value.Self() != nil {
			scalar := t.AsScalar.Value.Self()
			row["asScalar"] = map[string]any{"name": scalar.Name, "description": scalar.Description, "sourceModuleName": scalar.SourceModuleName}
		}
		if t.AsEnum.Valid && t.AsEnum.Value.Self() != nil {
			enum := t.AsEnum.Value.Self()
			members := make([]map[string]any, 0, len(enum.Members))
			for _, value := range enum.Members {
				member := value.Self()
				if member == nil {
					return nil, fmt.Errorf("nil enum member in CLI metadata")
				}
				members = append(members, map[string]any{"name": member.Name, "description": member.Description})
			}
			row["asEnum"] = map[string]any{"name": enum.Name, "description": enum.Description, "sourceModuleName": enum.SourceModuleName, "members": members}
		}
		if t.AsInput.Valid && t.AsInput.Value.Self() != nil {
			input := t.AsInput.Value.Self()
			fields, err := cliFields(input.Fields)
			if err != nil {
				return nil, err
			}
			row["asInput"] = map[string]any{"name": input.Name, "fields": fields}
		}
		if t.AsList.Valid && t.AsList.Value.Self() != nil {
			element, err := cliTypeRef(t.AsList.Value.Self().ElementTypeDef)
			if err != nil {
				return nil, err
			}
			row["asList"] = map[string]any{"elementTypeDef": element}
		}
		rows = append(rows, row)
	}
	data, err := json.Marshal(rows)
	return core.JSON(data), err
}
