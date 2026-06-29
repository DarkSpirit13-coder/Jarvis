<!-- Architecture overview for the JARVIS monorepo. -->
# JARVIS Architecture

JARVIS is organized as a clean monorepo with a FastAPI backend, a Next.js 15 frontend, an Electron desktop shell, and Dockerized infrastructure.

The backend exposes HTTP and WebSocket boundaries, then delegates work to services, agents, memory, voice, and tool abstractions. External systems are represented by interfaces and configured implementations, so production providers can be introduced without rewriting API handlers.

The frontend is a typed operational console that consumes backend health and real-time channels through small library and hook layers.

