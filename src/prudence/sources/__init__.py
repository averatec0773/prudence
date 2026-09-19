"""Sources: where Prudence sees the developer's work.

One module per agent (Claude Code first). A source finds the agent's local data and
reads it; it never writes to the agent's files and never touches the Prudence store
directly. An interface shared by several sources is extracted when the second source
arrives, not before.
"""
