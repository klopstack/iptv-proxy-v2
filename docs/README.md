# Documentation Index

This directory contains the core documentation for IPTV Proxy v2. The documentation has been streamlined to focus on essential information for users and developers.

## Documentation Structure

### [ARCHITECTURE.md](ARCHITECTURE.md)
**For: Developers, System Architects**

Comprehensive overview of the system architecture, including:
- High-level system design and data flow
- Core components and services
- Database model relationships
- Tag extraction system design
- Performance considerations and best practices
- External integrations (Xtream Codes, Schedules Direct, TheSportsDB)

### [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
**For: Contributors, Developers**

Complete guide for setting up and contributing to the project:
- Development environment setup
- Testing requirements and best practices
- Code quality standards and tools
- Database migration patterns
- Common development workflows
- Performance guidelines
- Contributing guidelines and PR process

### [API_REFERENCE.md](API_REFERENCE.md)
**For: Integrators, Advanced Users**

Comprehensive API documentation covering:
- All REST API endpoints with examples
- Xtream Codes API compatibility layer
- Playlist and EPG generation endpoints
- Authentication and error handling
- Rate limiting and best practices
- SDK examples in Python and JavaScript

### [XTREAM_CODES_API.md](XTREAM_CODES_API.md)
**For: End Users, IPTV Client Users**

User-friendly guide for the Xtream Codes API feature:
- Quick setup instructions for popular IPTV clients
- Configuration examples for TiviMate, IPTV Smarters, etc.
- Feature overview and compatibility information
- Troubleshooting common issues

### [todos/](todos/README.md)
**For: Maintainers, Active Development**

Work backlog from codebase audits (May–June 2026). Prioritized items (P0–P6) with problem statements, proposed solutions, acceptance criteria, and test plans. Work through [todos/README.md](todos/README.md) in order.

### [DEPLOYMENT.md](DEPLOYMENT.md)
**For: Operators**

Traefik + Authentik forward-auth for admin vs client paths. Derived from the [klopstack](https://github.com/klopstack/klopstack) stack (`iptvproxy` service labels).

### [architecture/](architecture/)
**For: Maintainers, Architecture Review**

Draft architecture documents from June 2026 audits — PPV pipeline, auth/security, API contracts, EPG/sync, frontend debt, schema lifecycle. Review before large refactors. See also [PPV_ARCHITECTURE.md](PPV_ARCHITECTURE.md) for a quick PPV entry point.

## Quick Navigation

### I want to...

**Understand how the system works**
→ Start with [ARCHITECTURE.md](ARCHITECTURE.md)

**Set up a development environment**
→ Follow [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md#development-setup)

**Contribute code or fix bugs**
→ Read [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md#contributing-guidelines)

**Integrate with the API**
→ Reference [API_REFERENCE.md](API_REFERENCE.md)

**Connect my IPTV client**
→ Follow [XTREAM_CODES_API.md](XTREAM_CODES_API.md)

**Understand the tag extraction system**
→ See [ARCHITECTURE.md#tag-extraction-system](ARCHITECTURE.md#tag-extraction-system)

**Run tests and check code quality**
→ Use commands in [DEVELOPER_GUIDE.md#testing](DEVELOPER_GUIDE.md#testing)

**See planned fixes and audit backlog**
→ Start with [todos/README.md](todos/README.md)

**Review architecture before large refactors**
→ See [architecture/](architecture/)

## Changelog

**January 6, 2026**: Documentation restructured and consolidated
- Removed 80+ outdated implementation and fix documentation files
- Consolidated into 4 focused, comprehensive guides
- Added this index for easy navigation
- Combined architecture overview with technical details
- Merged testing, development, and contribution information

## For Maintainers

When adding new documentation:
1. **Check if it fits in existing files first** - avoid creating new files unless absolutely necessary
2. **Update this index** if new files are created
3. **Remove outdated content** rather than adding notes about deprecation
4. **Keep user-facing docs separate** from internal implementation details
5. **Test all examples** and code snippets before committing

The goal is to maintain a clean, focused documentation set that serves both newcomers and experienced developers without overwhelming either group.
