# CaptainStems - Product Context

## Problem Statement

Audio source separation has traditionally been:

- Technically complex, requiring command-line knowledge
- Dependent on complex AI model installation
- Difficult to set up across different operating systems
- Inaccessible to non-technical users who need the functionality

## Solution

CaptainStems solves these problems by providing:

1. A graphical user interface with drag-and-drop functionality
2. Automatic handling of complex dependencies
3. Cross-platform compatibility (macOS and Windows)
4. Support for multiple AI models with different strengths
5. Interactive visualization and playback of results

## User Experience Goals

- **Simplicity**: Allow users to separate audio with just a few clicks
- **Flexibility**: Support multiple AI models with different separation capabilities
- **Visual Feedback**: Provide waveform visualization and playback to verify results
- **Format Support**: Handle a wide range of audio formats through FFmpeg integration
- **Graceful Degradation**: Application remains functional even without all AI models installed

## User Flow

1. User launches application
2. User drags and drops one or more audio files (or folders) into the application
3. User selects desired AI model for source separation
4. User clicks "Process" button
5. Application shows progress during processing
6. Results window appears with separated stems (for a batch: on double-click of a finished file)
7. User can play, preview, and save stems individually or all at once, in the format of their choice

## User Feedback

The application should provide clear feedback at all stages:

- Installation status for dependencies
- Audio file validation
- Processing progress
- Preview of separation results
- Success/failure of export operations

## Competitive Landscape

- Command-line tools (Demucs, Spleeter): powerful but technically complex
- Web services (LALAL.AI, PhonicMind): easy to use but require internet and often subscription fees
- Professional DAW plugins: expensive and require host software

CaptainStems combines the power of open-source AI models with the accessibility of a dedicated application at no cost.
