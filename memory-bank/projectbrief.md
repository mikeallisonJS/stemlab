# CaptainStems - Project Brief

## Project Overview

CaptainStems is a cross-platform GUI application built in Python that enables users to separate audio tracks into their component stems (vocals, instruments, etc.) using AI-powered source separation models.

## Core Objectives

1. Provide an **intuitive user interface** for audio source separation that requires no technical knowledge
2. Support **multiple AI models** for audio separation (Demucs v3/v4, Spleeter, Band-Split RNN, D3Net)
3. Create a **cross-platform solution** that works consistently on macOS and Windows
4. Allow for **easy installation** of complex dependencies
5. Implement an **interactive results interface** with waveform visualization and playback

## Target Users

- Musicians and producers who want to extract specific elements from mixed audio
- DJs who need to separate tracks for remixing
- Content creators who need to isolate vocals or instruments
- Music enthusiasts with limited technical knowledge

## Success Criteria

- Application can successfully separate audio using at least 2 different AI models
- Users can save separated stems in multiple formats
- Application runs reliably on both macOS and Windows
- Installation process handles complex dependencies gracefully
- GUI is intuitive and requires minimal documentation to use

## Constraints

- Must support Python 3.10 for best compatibility with AI models
- Must provide fallbacks for newer Python versions (3.11+)
- Must handle platform-specific quirks (Apple Silicon, CPU vs GPU)
- Must accommodate various audio formats through FFmpeg
