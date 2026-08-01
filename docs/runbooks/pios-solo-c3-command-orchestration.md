# PIOS Solo C3 Command Orchestration

Status: developer-only, disabled by default. This package does not authorize or
run a C3 Unix-socket session.

## Purpose

`scripts/plan_pios_solo_c3_command_orchestration.py` defines the one future
parent process that can coordinate the reviewed Solo one-shot server and the
reviewed Corebox developer tool. It solves process ordering only: the server
must bind a fresh private socket before the Corebox tool receives its ephemeral
runtime/socket arguments.

The command has no endpoint, credential, device enrollment, app setting,
background process, VM, cloud, or personal-data parameter.

## Required Named Inputs

Every future invocation supplies all of these explicit values:

- fixed four-artifact C2 fixture directory;
- new C3 proof ID and whole-second UTC receipt timestamp;
- existing absolute non-symlink runtime parent;
- fresh evidence directory that does not already exist;
- executable regular non-symlink Corebox developer-tool path;
- Solo server revision `2ccfa0c`; and
- Corebox client revision `1566817`.

The orchestrator validates these inputs and reuses the C3 zero-write fixture
validation before it may consider listener setup. Its normal output is a
sanitized `prepared_not_authorized` plan. It does not print local paths or a
child command.

## Internal Future Sequence

The disabled internal function would perform exactly this order:

1. validate named inputs and the fixed fixture;
2. create a fresh `0700` private runtime directory and bind `handoff.sock`;
3. construct the Corebox developer-tool child command only from that fresh
   runtime/socket pair;
4. start one Corebox child with no stdin;
5. accept one same-EUID AF_UNIX peer, apply timeouts, and exchange one accepted
   request plus one exact duplicate;
6. compare the Corebox and Solo receipt IDs;
7. close the child/connection/listener, remove socket/runtime/lifecycle roots,
   and retain only sanitized Solo evidence.

The child tool independently validates the named command shape and remains
hard-disabled before it creates its AF_UNIX channel or reads the fixture.

## Hard Disable

`ORCHESTRATION_EXECUTION_ENABLED` is `False`. Supplying
`--confirm-c3-local-transport-orchestration` builds and validates the plan, then
refuses before `subprocess.Popen`, listener creation, socket activity, fixture
submission, lifecycle work, or evidence writing.

Changing this gate is not an operational instruction. It requires a separate
reviewed source change, a named owner decision, and a new focused review of the
exact revisions and proof inputs.

## Validation

The local tests cover exact revision binding, regular executable tool checks,
sanitized preview output, confirmation refusal before child start, and the
server listener-ready callback ordering. They do not open a real socket or
start a Corebox child.

## Non-Authorization

This package does not authorize execution, a C3 proof, persistent local
transport, app networking, Solo Owner Bind, credentials, personal data,
background synchronization, VM changes, cloud actions, or an import/export.
