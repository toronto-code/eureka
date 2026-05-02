"""Default permission rules - Cursor-style allowlist for safe operations."""

from mycelium_agent_runtime.permissions.rules import (
    ActionType,
    PermissionLevel,
    PermissionRule,
)


def get_default_rules() -> list[PermissionRule]:
    """Return the default permission rules.

    Philosophy (like Cursor):
    - Auto-approve read-only and navigation commands
    - Require approval for writes, deletes, and network operations
    - Block dangerous operations entirely
    """
    rules: list[PermissionRule] = []

    # =========================================================================
    # BLOCKED - Never allow these
    # =========================================================================

    rules.append(
        PermissionRule(
            name="block_sudo",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.BLOCKED,
            description="sudo commands are never allowed",
            command_pattern=r"^\s*sudo\s",
            priority=1000,
        )
    )

    rules.append(
        PermissionRule(
            name="block_su",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.BLOCKED,
            description="su commands are never allowed",
            command_pattern=r"^\s*su\s",
            priority=1000,
        )
    )

    rules.append(
        PermissionRule(
            name="block_chmod_dangerous",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.BLOCKED,
            description="Dangerous chmod patterns are blocked",
            command_pattern=r"chmod\s+[0-7]*7[0-7]*[0-7]*\s",
            priority=1000,
        )
    )

    rules.append(
        PermissionRule(
            name="block_rm_rf_root",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.BLOCKED,
            description="rm -rf on root is blocked",
            command_pattern=r"rm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+/(\s|$|\*)",
            priority=1000,
        )
    )

    rules.append(
        PermissionRule(
            name="block_rm_rf_home",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.BLOCKED,
            description="rm -rf on home directory is blocked",
            command_pattern=r"rm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+(~|\$HOME)(\s|$|/)",
            priority=1000,
        )
    )

    rules.append(
        PermissionRule(
            name="block_env_secrets",
            action_type=ActionType.FILE_READ,
            level=PermissionLevel.BLOCKED,
            description="Reading .env files with secrets is blocked",
            command_pattern=None,
            path_pattern="**/.env*",
            priority=1000,
        )
    )

    rules.append(
        PermissionRule(
            name="block_ssh_keys",
            action_type=ActionType.FILE_READ,
            level=PermissionLevel.BLOCKED,
            description="Reading SSH private keys is blocked",
            path_pattern="**/.ssh/id_*",
            priority=1000,
        )
    )

    rules.append(
        PermissionRule(
            name="block_credentials",
            action_type=ActionType.FILE_READ,
            level=PermissionLevel.BLOCKED,
            description="Reading credential files is blocked",
            path_pattern="**/credentials*",
            priority=1000,
        )
    )

    # =========================================================================
    # AUTO - Safe read-only operations
    # =========================================================================

    safe_read_commands = [
        ("auto_ls", r"^\s*ls(\s|$)", "List directory contents"),
        ("auto_pwd", r"^\s*pwd(\s|$)", "Print working directory"),
        ("auto_cat", r"^\s*cat\s", "Read file contents"),
        ("auto_head", r"^\s*head\s", "Read file head"),
        ("auto_tail", r"^\s*tail\s", "Read file tail"),
        ("auto_less", r"^\s*less\s", "View file contents"),
        ("auto_more", r"^\s*more\s", "View file contents"),
        ("auto_wc", r"^\s*wc\s", "Word/line count"),
        ("auto_grep", r"^\s*grep\s", "Search file contents"),
        ("auto_rg", r"^\s*rg\s", "Ripgrep search"),
        ("auto_find", r"^\s*find\s", "Find files"),
        ("auto_fd", r"^\s*fd\s", "Find files (fd)"),
        ("auto_which", r"^\s*which\s", "Locate command"),
        ("auto_whereis", r"^\s*whereis\s", "Locate binary"),
        ("auto_type", r"^\s*type\s", "Show command type"),
        ("auto_file", r"^\s*file\s", "Determine file type"),
        ("auto_stat", r"^\s*stat\s", "File statistics"),
        ("auto_du", r"^\s*du\s", "Disk usage"),
        ("auto_df", r"^\s*df\s", "Disk free space"),
        ("auto_echo", r"^\s*echo\s", "Print text"),
        ("auto_printf", r"^\s*printf\s", "Print formatted text"),
        ("auto_date", r"^\s*date(\s|$)", "Show date/time"),
        ("auto_whoami", r"^\s*whoami(\s|$)", "Show current user"),
        ("auto_hostname", r"^\s*hostname(\s|$)", "Show hostname"),
        ("auto_uname", r"^\s*uname\s", "System information"),
        ("auto_env_show", r"^\s*env(\s|$)", "Show environment"),
        ("auto_printenv", r"^\s*printenv(\s|$)", "Print environment"),
        ("auto_tree", r"^\s*tree\s", "Directory tree"),
        ("auto_realpath", r"^\s*realpath\s", "Resolve path"),
        ("auto_dirname", r"^\s*dirname\s", "Directory name"),
        ("auto_basename", r"^\s*basename\s", "Base name"),
    ]

    for name, pattern, desc in safe_read_commands:
        rules.append(
            PermissionRule(
                name=name,
                action_type=ActionType.SHELL_COMMAND,
                level=PermissionLevel.AUTO,
                description=desc,
                command_pattern=pattern,
                priority=100,
            )
        )

    # Git read operations (auto)
    git_read_commands = [
        ("auto_git_status", r"^\s*git\s+status(\s|$)", "Git status"),
        ("auto_git_log", r"^\s*git\s+log(\s|$)", "Git log"),
        ("auto_git_diff", r"^\s*git\s+diff(\s|$)", "Git diff"),
        ("auto_git_show", r"^\s*git\s+show(\s|$)", "Git show"),
        ("auto_git_branch_list", r"^\s*git\s+branch(\s+-[avrl])*\s*$", "Git branch list"),
        ("auto_git_remote", r"^\s*git\s+remote(\s+-v)?(\s|$)", "Git remote"),
        ("auto_git_config_list", r"^\s*git\s+config\s+(-l|--list)", "Git config list"),
        ("auto_git_rev_parse", r"^\s*git\s+rev-parse(\s|$)", "Git rev-parse"),
        ("auto_git_describe", r"^\s*git\s+describe(\s|$)", "Git describe"),
        ("auto_git_ls_files", r"^\s*git\s+ls-files(\s|$)", "Git ls-files"),
        ("auto_git_ls_tree", r"^\s*git\s+ls-tree(\s|$)", "Git ls-tree"),
        ("auto_git_blame", r"^\s*git\s+blame(\s|$)", "Git blame"),
        ("auto_git_shortlog", r"^\s*git\s+shortlog(\s|$)", "Git shortlog"),
        ("auto_git_stash_list", r"^\s*git\s+stash\s+list(\s|$)", "Git stash list"),
        ("auto_git_tag_list", r"^\s*git\s+tag(\s+-l)?(\s|$)", "Git tag list"),
    ]

    for name, pattern, desc in git_read_commands:
        rules.append(
            PermissionRule(
                name=name,
                action_type=ActionType.SHELL_COMMAND,
                level=PermissionLevel.AUTO,
                description=desc,
                command_pattern=pattern,
                priority=100,
            )
        )

    # Navigation commands (auto)
    rules.append(
        PermissionRule(
            name="auto_cd",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.AUTO,
            description="Change directory",
            command_pattern=r"^\s*cd(\s|$)",
            priority=100,
        )
    )

    # File read is auto (except blocked patterns above)
    rules.append(
        PermissionRule(
            name="auto_file_read",
            action_type=ActionType.FILE_READ,
            level=PermissionLevel.AUTO,
            description="Reading files is allowed",
            priority=50,
        )
    )

    # Git read operations type
    rules.append(
        PermissionRule(
            name="auto_git_read",
            action_type=ActionType.GIT_READ,
            level=PermissionLevel.AUTO,
            description="Git read operations are allowed",
            priority=50,
        )
    )

    # =========================================================================
    # REQUIRES_APPROVAL - Write operations and network
    # =========================================================================

    # Git write operations
    git_write_commands = [
        ("approve_git_add", r"^\s*git\s+add(\s|$)", "Stage changes"),
        ("approve_git_commit", r"^\s*git\s+commit(\s|$)", "Commit changes"),
        ("approve_git_push", r"^\s*git\s+push(\s|$)", "Push to remote"),
        ("approve_git_pull", r"^\s*git\s+pull(\s|$)", "Pull from remote"),
        ("approve_git_fetch", r"^\s*git\s+fetch(\s|$)", "Fetch from remote"),
        ("approve_git_merge", r"^\s*git\s+merge(\s|$)", "Merge branches"),
        ("approve_git_rebase", r"^\s*git\s+rebase(\s|$)", "Rebase branch"),
        ("approve_git_checkout", r"^\s*git\s+checkout(\s|$)", "Checkout branch/files"),
        ("approve_git_switch", r"^\s*git\s+switch(\s|$)", "Switch branch"),
        ("approve_git_branch_create", r"^\s*git\s+branch\s+[^-]", "Create branch"),
        ("approve_git_reset", r"^\s*git\s+reset(\s|$)", "Reset changes"),
        ("approve_git_stash", r"^\s*git\s+stash(\s|$)", "Stash changes"),
        ("approve_git_cherry_pick", r"^\s*git\s+cherry-pick(\s|$)", "Cherry-pick"),
        ("approve_git_revert", r"^\s*git\s+revert(\s|$)", "Revert commit"),
        ("approve_git_clean", r"^\s*git\s+clean(\s|$)", "Clean untracked"),
    ]

    for name, pattern, desc in git_write_commands:
        rules.append(
            PermissionRule(
                name=name,
                action_type=ActionType.SHELL_COMMAND,
                level=PermissionLevel.REQUIRES_APPROVAL,
                description=desc,
                command_pattern=pattern,
                priority=80,
            )
        )

    # File operations requiring approval
    rules.append(
        PermissionRule(
            name="approve_file_write",
            action_type=ActionType.FILE_WRITE,
            level=PermissionLevel.REQUIRES_APPROVAL,
            description="Writing files requires approval",
            priority=50,
        )
    )

    rules.append(
        PermissionRule(
            name="approve_file_delete",
            action_type=ActionType.FILE_DELETE,
            level=PermissionLevel.REQUIRES_APPROVAL,
            description="Deleting files requires approval",
            priority=50,
        )
    )

    rules.append(
        PermissionRule(
            name="approve_git_write",
            action_type=ActionType.GIT_WRITE,
            level=PermissionLevel.REQUIRES_APPROVAL,
            description="Git write operations require approval",
            priority=50,
        )
    )

    # Shell commands with pipes/redirects need approval
    rules.append(
        PermissionRule(
            name="approve_shell_pipe",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.REQUIRES_APPROVAL,
            description="Commands with pipes require approval",
            command_pattern=r"\|",
            priority=90,
        )
    )

    rules.append(
        PermissionRule(
            name="approve_shell_redirect",
            action_type=ActionType.SHELL_COMMAND,
            level=PermissionLevel.REQUIRES_APPROVAL,
            description="Commands with redirects require approval",
            command_pattern=r"[<>]",
            priority=90,
        )
    )

    # File modification commands
    modify_commands = [
        ("approve_rm", r"^\s*rm\s", "Remove files"),
        ("approve_rmdir", r"^\s*rmdir\s", "Remove directory"),
        ("approve_mv", r"^\s*mv\s", "Move/rename files"),
        ("approve_cp", r"^\s*cp\s", "Copy files"),
        ("approve_mkdir", r"^\s*mkdir\s", "Create directory"),
        ("approve_touch", r"^\s*touch\s", "Create/update file"),
        ("approve_chmod", r"^\s*chmod\s", "Change permissions"),
        ("approve_chown", r"^\s*chown\s", "Change ownership"),
        ("approve_ln", r"^\s*ln\s", "Create link"),
        ("approve_unlink", r"^\s*unlink\s", "Remove link"),
    ]

    for name, pattern, desc in modify_commands:
        rules.append(
            PermissionRule(
                name=name,
                action_type=ActionType.SHELL_COMMAND,
                level=PermissionLevel.REQUIRES_APPROVAL,
                description=desc,
                command_pattern=pattern,
                priority=80,
            )
        )

    # Network commands
    network_commands = [
        ("approve_curl", r"^\s*curl\s", "HTTP request via curl"),
        ("approve_wget", r"^\s*wget\s", "HTTP request via wget"),
        ("approve_ssh", r"^\s*ssh\s", "SSH connection"),
        ("approve_scp", r"^\s*scp\s", "Secure copy"),
        ("approve_rsync", r"^\s*rsync\s", "Remote sync"),
        ("approve_nc", r"^\s*nc\s", "Netcat"),
        ("approve_netcat", r"^\s*netcat\s", "Netcat"),
        ("approve_ping", r"^\s*ping\s", "Ping host"),
        ("approve_nslookup", r"^\s*nslookup\s", "DNS lookup"),
        ("approve_dig", r"^\s*dig\s", "DNS lookup"),
        ("approve_host", r"^\s*host\s", "DNS lookup"),
    ]

    for name, pattern, desc in network_commands:
        rules.append(
            PermissionRule(
                name=name,
                action_type=ActionType.SHELL_COMMAND,
                level=PermissionLevel.REQUIRES_APPROVAL,
                description=desc,
                command_pattern=pattern,
                priority=80,
            )
        )

    # HTTP requests require approval
    rules.append(
        PermissionRule(
            name="approve_http",
            action_type=ActionType.HTTP_REQUEST,
            level=PermissionLevel.REQUIRES_APPROVAL,
            description="HTTP requests require approval",
            priority=50,
        )
    )

    # Code execution requires approval
    rules.append(
        PermissionRule(
            name="approve_code_exec",
            action_type=ActionType.CODE_EXECUTION,
            level=PermissionLevel.REQUIRES_APPROVAL,
            description="Code execution requires approval",
            priority=50,
        )
    )

    # Package managers require approval
    package_commands = [
        ("approve_npm", r"^\s*npm\s+(install|uninstall|update|publish)", "npm package operations"),
        ("approve_yarn", r"^\s*yarn\s+(add|remove|upgrade|publish)", "yarn package operations"),
        ("approve_pnpm", r"^\s*pnpm\s+(add|remove|update|publish)", "pnpm package operations"),
        ("approve_pip", r"^\s*pip\s+(install|uninstall)", "pip package operations"),
        ("approve_pip3", r"^\s*pip3\s+(install|uninstall)", "pip3 package operations"),
        ("approve_poetry", r"^\s*poetry\s+(add|remove|update|publish)", "poetry package operations"),
        ("approve_brew", r"^\s*brew\s+(install|uninstall|upgrade)", "homebrew operations"),
        ("approve_apt", r"^\s*apt(-get)?\s+(install|remove|update|upgrade)", "apt operations"),
    ]

    for name, pattern, desc in package_commands:
        rules.append(
            PermissionRule(
                name=name,
                action_type=ActionType.SHELL_COMMAND,
                level=PermissionLevel.REQUIRES_APPROVAL,
                description=desc,
                command_pattern=pattern,
                priority=80,
            )
        )

    return rules
