# CaptainStems - Active Context

## Current Focus

The project is currently in development with focus on:

1. Setting up project structure and documentation
2. Implementing the core UI components
3. Integrating multiple AI models for audio separation

## Active Decisions

### Memory Bank Initialization

- Memory bank is being established to maintain project continuity
- Documentation will track progress and important decisions
- Will serve as the source of truth for the project state

### Python Version Strategy

- Primary target is Python 3.10.x for maximum compatibility
- Support scripts help manage environment setup and compatibility
- Graceful degradation for newer Python versions

### User Experience Priorities

- Focus on simplicity and intuitive interaction
- Drag-and-drop functionality as primary input method
- Clear visual feedback during processing
- Interactive audio playback for results

## Recent Changes

- Project structure has been established
- Core files have been created
- Basic launcher scripts are in place
- Memory bank has been initialized

## Next Steps

### Short-term

- Implement the main UI with drag-and-drop area
- Create the AI model manager with basic interface
- Set up initial model (Demucs v4) integration
- Implement basic audio file validation

### Medium-term

- Add additional model support (Spleeter, Band-Split RNN, D3Net)
- Develop the results window with waveform visualization
- Implement audio playback for separated stems
- Add export functionality for all formats

### Long-term

- Optimize performance for large audio files
- Enhance GPU acceleration across platforms
- Add batch processing capabilities
- Implement settings for advanced users

## Open Questions

- Best approach for handling extremely large audio files
- Optimal thread management for UI responsiveness
- Storage strategy for model weights and temporary files
- User preferences persistence method
