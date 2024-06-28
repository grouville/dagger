package schema

// // gitCLI carries config to pass to the git CLI to make running multiple
// // commands less repetitive.
// //
// // It may also contain references to config files that should be cleaned up
// // when the CLI is done being used.
// type gitCLI struct {
// 	sshAuthSock string // SSH_AUTH_SOCK env value
// 	knownHosts  string // file path passed to SSH

// 	hostsPath  string // generated /etc/hosts from network config
// 	resolvPath string // generated /etc/resolv.conf from network config
// }

// // newGitCLI constructs a gitCLI and returns its cleanup function explicitly so
// // it's harder to forget to call it.
// func newGitCLI(
// 	SSHAuthSocket *core.Socket,

// 	sshAuthSock,
// 	knownHosts string,

// ) (*gitCLI, func(), error) {
// 	cli := &gitCLI{
// 		sshAuthSock: sshAuthSock,
// 		knownHosts:  knownHosts,
// 	}

// 	bk.SessionManager.Get(ctx, d.sessionID, true)

// 	// if err := cli.initConfig(); err != nil {
// 	// 	cli.cleanup()
// 	// 	return nil, nil, err
// 	// }
// 	return cli, cli.cleanup, nil
// }

// func (cli *gitCLI) initConfig() {

// }

// func (cli *gitCLI) cleanup() {
// 	if cli.hostsPath != "" {
// 		os.Remove(cli.hostsPath)
// 	}
// 	if cli.resolvPath != "" {
// 		os.Remove(cli.resolvPath)
// 	}
// }

// func (cli *gitCLI) run(ctx context.Context, args ...string) (_ *bytes.Buffer, err error) {
// 	for {
// 		stdout, stderr, flush := logs.NewLogStreams(ctx, true)
// 		defer stdout.Close()
// 		defer stderr.Close()
// 		defer func() {
// 			if err != nil {
// 				flush()
// 			}
// 		}()

// 		cmd := exec.Command("git")
// 		// Block sneaky repositories from using repos from the filesystem as submodules.
// 		cmd.Args = append(cmd.Args, "-c", "protocol.file.allow=user")
// 		if len(cli.auth) > 0 {
// 			cmd.Args = append(cmd.Args, cli.auth...)
// 		}
// 		cmd.Args = append(cmd.Args, args...)

// 		cmd.Dir = cli.workTree // some commands like submodule require this
// 		buf := bytes.NewBuffer(nil)
// 		errbuf := bytes.NewBuffer(nil)
// 		cmd.Stdin = nil
// 		cmd.Stdout = io.MultiWriter(stdout, buf)
// 		cmd.Stderr = io.MultiWriter(stderr, errbuf)
// 		cmd.Env = []string{
// 			"PATH=" + os.Getenv("PATH"),
// 			"GIT_TERMINAL_PROMPT=0",
// 			"GIT_SSH_COMMAND=" + getGitSSHCommand(cli.knownHosts),
// 			//	"GIT_TRACE=1",
// 			"GIT_CONFIG_NOSYSTEM=1", // Disable reading from system gitconfig.
// 			"HOME=/dev/null",        // Disable reading from user gitconfig.
// 			"LC_ALL=C",              // Ensure consistent output.
// 		}

// 		if cli.sshAuthSock != "" {
// 			cmd.Env = append(cmd.Env, "SSH_AUTH_SOCK="+cli.sshAuthSock)
// 		}
// 		// remote git commands spawn helper processes that inherit FDs and don't
// 		// handle parent death signal so exec.CommandContext can't be used
// 		err := runWithStandardUmaskAndNetOverride(ctx, cmd, cli.hostsPath, cli.resolvPath)
// 		if err != nil {
// 			if strings.Contains(errbuf.String(), "--depth") || strings.Contains(errbuf.String(), "shallow") {
// 				if newArgs := argsNoDepth(args); len(args) > len(newArgs) {
// 					args = newArgs
// 					continue
// 				}
// 			}
// 			return buf, errors.Errorf("git error: %s\nstderr:\n%s", err, errbuf.String())
// 		}
// 		return buf, nil
// 	}
// }

// func getGitSSHCommand(knownHosts string) string {
// 	gitSSHCommand := "ssh -F /dev/null"
// 	if knownHosts != "" {
// 		gitSSHCommand += " -o UserKnownHostsFile=" + knownHosts
// 	} else {
// 		gitSSHCommand += " -o StrictHostKeyChecking=no"
// 	}
// 	return gitSSHCommand
// }

// func runWithStandardUmaskAndNetOverride(ctx context.Context, cmd *exec.Cmd, hosts, resolv string) error {
// 	errCh := make(chan error)

// 	go func() {
// 		defer close(errCh)
// 		runtime.LockOSThread()

// 		if err := unshareAndRun(ctx, cmd, hosts, resolv); err != nil {
// 			errCh <- err
// 		}
// 	}()

// 	return <-errCh
// }

// // unshareAndRun needs to be called in a locked thread.
// func unshareAndRun(ctx context.Context, cmd *exec.Cmd, hosts, resolv string) error {
// 	if err := syscall.Unshare(syscall.CLONE_FS | syscall.CLONE_NEWNS); err != nil {
// 		return err
// 	}
// 	syscall.Umask(0022)
// 	if err := overrideNetworkConfig(hosts, resolv); err != nil {
// 		return errors.Wrapf(err, "failed to override network config")
// 	}
// 	return runProcessGroup(ctx, cmd)
// }

// func runProcessGroup(ctx context.Context, cmd *exec.Cmd) error {
// 	cmd.SysProcAttr = &unix.SysProcAttr{
// 		Setpgid:   true,
// 		Pdeathsig: unix.SIGTERM,
// 	}
// 	if err := cmd.Start(); err != nil {
// 		return err
// 	}
// 	waitDone := make(chan struct{})
// 	go func() {
// 		select {
// 		case <-ctx.Done():
// 			_ = unix.Kill(-cmd.Process.Pid, unix.SIGTERM)
// 			go func() {
// 				select {
// 				case <-waitDone:
// 				case <-time.After(10 * time.Second):
// 					_ = unix.Kill(-cmd.Process.Pid, unix.SIGKILL)
// 				}
// 			}()
// 		case <-waitDone:
// 		}
// 	}()
// 	err := cmd.Wait()
// 	close(waitDone)
// 	return err
// }

// func overrideNetworkConfig(hostsOverride, resolvOverride string) error {
// 	if hostsOverride != "" {
// 		if err := mount.Mount(hostsOverride, "/etc/hosts", "", "bind"); err != nil {
// 			return errors.Wrap(err, "mount hosts override")
// 		}
// 	}

// 	if resolvOverride != "" {
// 		if err := syscall.Mount(resolvOverride, "/etc/resolv.conf", "", syscall.MS_BIND, ""); err != nil {
// 			return errors.Wrap(err, "mount resolv override")
// 		}
// 	}

// 	return nil
// }
