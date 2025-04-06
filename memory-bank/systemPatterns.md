# CaptainStems - System Patterns

## Architecture Overview

CaptainStems follows a **Model-View-Controller (MVC)** architecture:

- **Models** (`models/` directory): Handle audio processing and AI model interfacing
- **Views** (`ui/` directory): Implement the user interface components
- **Controller** (`main.py` and related files): Orchestrate the application flow

## Design Patterns

### 1. Factory Pattern

- Used for creating instances of different audio separation models
- Allows for a unified interface across different AI models

### 2. Observer Pattern

- Implemented to update the UI when processing state changes
- Enables progress tracking during lengthy operations

### 3. Adapter Pattern

- Adapts different AI model outputs into a standardized format
- Provides consistent stem handling regardless of the source model

### 4. Strategy Pattern

- Allows switching between different AI models
- Enables easy addition of new separation strategies

## Key Technical Decisions

### PyQt6 as UI Framework

- Modern cross-platform GUI capabilities
- Native look and feel on both macOS and Windows
- Rich widget toolkit suitable for complex audio interfaces

### Python 3.10 Compatibility

- Primary target for optimal AI model compatibility
- Script-based compatibility layer for newer Python versions

### AI Model Integration

- Loose coupling to support multiple models
- On-demand installation of model dependencies
- Fallback mechanisms for unavailable models

### Dependency Management

- Specialized scripts for installing complex dependencies
- Compatibility fixing scripts for edge cases
- Integrated dependency checking at startup

## Component Relationships

```
+----------------------+        +--------------------+
| MainWindow           |<------>| AudioDropArea      |
| (Controller)         |        | (View Component)   |
+----------------------+        +--------------------+
         |
         |
         v
+----------------------+        +--------------------+
| ModelManager         |<------>| DemucsModel        |
| (Factory)            |------->| SpleeterModel      |
+----------------------+------->| BandSplitModel     |
         |              \------>| D3NetModel         |
         |                      +--------------------+
         v
+----------------------+        +--------------------+
| ResultsWindow        |<------>| WaveformDisplay    |
| (View)               |<------>| AudioPlayer        |
+----------------------+        +--------------------+
```

## Error Handling Strategy

- Exception catching at model boundaries
- Graceful fallbacks for missing dependencies
- User-friendly error messages
- Detailed logging for debugging

## Performance Considerations

- Offloading heavy processing to background threads
- Progress tracking for long-running operations
- Support for GPU acceleration where available
- Memory efficient handling of audio data
