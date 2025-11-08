# Copilot Instructions for cn_auto_exports_app

## Project Overview

This is a Python-based Bokeh visualization application that displays and analyzes Chinese auto exports data. The application provides interactive maps and charts for exploring automotive export trends across different countries and time periods.

## Technology Stack

- **Python 3.10.14**
- **Bokeh 3.4.1** - Interactive visualization library
- **Pandas 2.2.2** - Data manipulation and analysis
- **GeoPandas 0.14.3** - Geographical data handling
- **NumPy 1.26.4** - Numerical computations
- **Matplotlib 3.8.4** - Color palette generation
- **Shapely 2.0.4** - Geometric operations
- **Tornado 6.4.1** - Web server framework
- **Jinja2 3.1.4** - Template engine

## Project Structure

```
cn_auto_exports_app/
├── app/
│   ├── main.py           # Main Bokeh application
│   └── data/             # Data files (CSV, shapefiles, GeoJSON)
├── templates/            # HTML templates
│   └── index.html
├── static/              # Static assets
├── requirements.txt     # Python dependencies
├── runtime.txt         # Python version for Heroku
├── Procfile           # Heroku deployment configuration
└── .github/           # GitHub configuration
```

## Key Files

- **`app/main.py`**: The main Bokeh server application containing all visualization logic, data processing, and UI components
- **`requirements.txt`**: All Python dependencies required for the application
- **`Procfile`**: Heroku configuration for running the Bokeh server
- **`runtime.txt`**: Specifies Python 3.10.14 for Heroku deployment

## Coding Conventions

### Python Style
- Follow PEP 8 guidelines
- Use type hints where appropriate (as seen with `Optional`, `RequestHandler`)
- Use meaningful variable names
- Prefer explicit imports over wildcard imports

### Code Organization
- Keep related functionality together
- Use comments to delineate major sections (e.g., `# --- THEME ---`)
- Handle optional dependencies gracefully with try-except blocks (e.g., GeoPandas fallback)

### Data Handling
- Use Pandas for data manipulation
- Support both GeoPandas (with shapefiles) and plain GeoJSON for geographical data
- Normalize column names for consistency (e.g., always use 'geometry' for spatial data)
- Handle missing data gracefully

### UI Components
- Use Bokeh's layout system (column, row) for organizing components
- Apply consistent theming through `curdoc().theme`
- Use Georgia font family for text elements
- Maintain color palette consistency using the defined `color_map`

## Dependencies Management

- All dependencies are listed in `requirements.txt`
- Pin specific versions to ensure reproducibility
- Core dependencies:
  - Bokeh for visualization
  - Pandas/GeoPandas for data handling
  - NumPy for numerical operations
  - Matplotlib for color utilities

## Deployment

### Heroku
- Application is deployed on Heroku
- Uses Bokeh server mode with specific configuration:
  - Port: `$PORT` (provided by Heroku)
  - Address: `0.0.0.0`
  - Allows WebSocket origin: `cn-auto-exports-304fc1cbcf39.herokuapp.com`
  - Uses X-Headers for proper proxy handling

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run the Bokeh server
bokeh serve app --show
```

## Data Files

The application expects data files in `app/data/`:
- **`auto_total.csv`**: Auto export data
- **`ne_10m_admin_0_countries.shp`**: World countries shapefile (optional)
- **`ne_10m_admin_0_countries.geojson`**: World countries GeoJSON (preferred for Heroku)

## Development Guidelines

### When Adding Features
1. Maintain compatibility with both GeoPandas and plain GeoJSON
2. Test with the Heroku-safe configuration (GeoJSON-based)
3. Keep the UI responsive and interactive
4. Follow the existing color scheme and theming
5. Use the established HTML formatter pattern for tables

### When Modifying Data Processing
1. Preserve data normalization patterns
2. Handle edge cases (missing data, empty results)
3. Maintain column naming conventions
4. Test with different data subsets

### When Updating UI
1. Use the existing theme configuration
2. Maintain Georgia font family consistency
3. Follow the established color palette
4. Keep layouts responsive
5. Ensure hover tools and interactions work properly

## Common Patterns

### Tier-based Content
The application supports tier-based content filtering:
```python
tier = get_tier_from_request()  # Returns "public" by default
```

### Geometry Handling
Always account for both GeoPandas and plain GeoJSON:
```python
if _using_gpd:
    # Use GeoPandas methods
else:
    # Use custom geometry functions
```

### Color Palettes
Use the interpolate_palette function for smooth color gradients:
```python
smooth_palette = interpolate_palette(custom_palette, 50)
```

## Testing

- Test locally before deploying
- Verify all visualizations render correctly
- Check data loading for both shapefile and GeoJSON paths
- Ensure WebSocket connections work properly

## Notes

- The application is designed to run on Heroku with limited filesystem support
- GeoJSON is preferred over shapefiles for cloud deployment
- The app uses Tornado request handlers for accessing query parameters
- Custom themes are applied at the document level using `curdoc().theme`
