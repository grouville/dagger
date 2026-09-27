package client

import "github.com/dagger/dagger/engine/session/attachables"

type Filesyncer = attachables.Filesyncer
type FilesyncSource = attachables.FilesyncSource
type FilesyncTarget = attachables.FilesyncTarget
type FilesyncSourceProxy = attachables.FilesyncSourceProxy
type FilesyncTargetProxy = attachables.FilesyncTargetProxy

func NewFilesyncer() (Filesyncer, error) { return attachables.NewFilesyncer() }
