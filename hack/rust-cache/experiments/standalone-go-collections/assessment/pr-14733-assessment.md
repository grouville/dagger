After looking at this again, I don't think the measured gain justifies the extra filesystem logic yet. The biggest improvement comes from selecting one path in a directory with 2,048 unrelated directories. In the smaller case, it saves about 8 microseconds per import.

That could add up if a command does enough of these imports, but I haven't verified a useful gain on main. I opened this too early, so I'm closing it for now. I'll revisit it if a real command shows that this is worth the added code.
