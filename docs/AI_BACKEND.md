# TTL Local AI Backend

TTL Local AI Backend is an independent desktop application that manages a local llama.cpp server for Tabletop Librarian or any compatible OpenAI-style client.

## What the Manager does

- detects available CPU/GPU hardware;
- recommends an appropriate backend;
- downloads the matching pinned llama.cpp runtime;
- downloads curated GGUF models or accepts an arbitrary local GGUF;
- starts/stops the llama.cpp server;
- displays the LAN address and configured port;
- generates/manages an API key;
- exposes advanced model/server options;
- optionally starts automatically at login;
- retains logs for troubleshooting.

Default port: **8081**.

## Backend selection policy

Normal recommendations are:

- NVIDIA discrete GPU: CUDA;
- AMD discrete GPU: Vulkan;
- Intel Arc discrete GPU: Vulkan;
- Intel integrated graphics: CPU fallback by default;
- no usable GPU: CPU fallback.

Integrated/older GPU Vulkan implementations vary widely. The Manager validates a downloaded runtime before treating it as usable and reports common Windows loader/driver failures.

CPU inference is functional but not recommended for interactive use with larger models.

## Connecting TTL Server

In the Server Knowledgebase/AI settings, configure an OpenAI-compatible provider pointing at the Backend Manager's address, for example:

```text
http://192.168.1.50:8081/v1
```

Use the API key shown by the Backend Manager and the model alias/name configured there.

## Server lifecycle

Stopping the local llama.cpp process from the Manager is treated as an intentional stop and does not display a false crash warning. Unexpected exits continue to surface diagnostics.

## Models

Models and llama.cpp runtimes are downloaded after installation and are not part of the TTL source repository or installer. This keeps release packages small and allows hardware-appropriate selection.
