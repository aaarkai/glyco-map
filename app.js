// Global data storage
let appData = {
    cgm: null,
    events: null,
    hypotheses: null,
    metrics: null,
    chart: null
};

// File upload handler
async function handleFileUpload(event, type) {
    const file = event.target.files[0];
    if (!file) return;

    // Update file info display
    const fileInfo = document.getElementById(`${type}FileInfo`);
    fileInfo.textContent = `${file.name} (${formatFileSize(file.size)})`;

    // Show loading indicator
    const loadingIndicator = document.getElementById('loadingIndicator');
    loadingIndicator.classList.remove('hidden');

    try {
        // Read and parse JSON
        const text = await file.text();
        const data = JSON.parse(text);

        // Store data
        appData[type] = data;
        console.log(`Loaded ${type} data:`, data);

        // Check for subject ID consistency
        checkSubjectConsistency();

        // Update UI when all required files are loaded
        if (appData.cgm && appData.events) {
            await Promise.all([
                visualizeCGM(),
                displayEvents(),
                displayHypotheses()
            ]);

            // Show visualization
            document.getElementById('visualizationSection').classList.add('active');
            document.getElementById('metricsSection').classList.add('active');

            // Display metrics if available
            if (appData.metrics) {
                displayMetrics();
            }
        }
    } catch (error) {
        console.error(`Error loading ${type} file:`, error);
        alert(`Error loading ${type} file: ${error.message}`);
        document.getElementById(`${type}FileInfo`).textContent = `Error: ${error.message}`;
    } finally {
        loadingIndicator.classList.add('hidden');
    }
}

// Check if subject IDs match across files
function checkSubjectConsistency() {
    const subjects = [];
    let subjectMismatchWarning = document.getElementById('subjectMismatchWarning');
    let subjectMismatchText = document.getElementById('subjectMismatchText');

    if (appData.cgm) subjects.push({ type: 'CGM', id: appData.cgm.subject_id || 'Unknown' });
    if (appData.events) subjects.push({ type: 'Events', id: appData.events.subject_id || 'Unknown' });
    if (appData.hypotheses) subjects.push({ type: 'Hypotheses', id: appData.hypotheses.subject_id || 'Unknown' });
    if (appData.metrics) subjects.push({ type: 'Metrics', id: appData.metrics.subject_id || 'Unknown' });

    if (subjects.length > 1) {
        const subjectIds = subjects.map(s => s.id);
        const uniqueIds = [...new Set(subjectIds)];

        if (uniqueIds.length > 1) {
            // Show mismatch warning
            const subjText = subjects.map(s => `${s.type}: ${s.id}`).join(', ');
            subjectMismatchText.textContent = `The uploaded files contain different subject IDs: ${subjText}. Please verify you're analyzing the same subject's data.`;
            subjectMismatchWarning.style.display = 'block';
        } else {
            subjectMismatchWarning.style.display = 'none';
        }
    }
}

// Visualize CGM data with Chart.js
async function visualizeCGM() {
    if (!appData.cgm || !appData.cgm.samples) {
        console.error('No CGM data to visualize');
        return;
    }

    const ctx = document.getElementById('cgmChart').getContext('2d');

    // Prepare data
    const samples = appData.cgm.samples
        .map(s => ({
            x: new Date(s.timestamp),
            y: s.glucose_value,
            qualityFlags: s.quality_flags || []
        }))
        .sort((a, b) => a.x - b.x);

    if (appData.chart) {
        appData.chart.destroy();
    }

    const datasets = [{
        label: `Glucose (${appData.cgm.unit})`,
        data: samples,
        borderColor: '#667eea',
        backgroundColor: 'rgba(102, 126, 234, 0.1)',
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.1,
        fill: true
    }];

    // Add quality flag indicators
    const flaggedSamples = samples.filter(s => s.qualityFlags.length > 0);
    if (flaggedSamples.length > 0) {
        datasets.push({
            label: 'Quality Issues',
            data: flaggedSamples,
            borderColor: '#ffc107',
            backgroundColor: '#ffc107',
            borderWidth: 3,
            pointRadius: 5,
            pointStyle: 'triangle',
            showLine: false,
            type: 'scatter'
        });
    }

    appData.chart = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                title: {
                    display: true,
                    text: `CGM Time Series - Subject: ${appData.cgm.subject_id || 'Unknown'}`,
                    font: { size: 18, weight: 'bold' }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y.toFixed(1) + ' ' + (appData.cgm.unit || 'mg/dL');
                            }
                            const sample = samples[context.dataIndex];
                            if (sample && sample.qualityFlags && sample.qualityFlags.length > 0) {
                                label += ` ⚠ ${sample.qualityFlags.join(', ')}`;
                            }
                            return label;
                        }
                    }
                },
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'MMM d, h:mm a'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: `Glucose (${appData.cgm.unit || 'mg/dL'})`
                    },
                    beginAtZero: false
                }
            },
            animation: {
                duration: 1000,
                easing: 'easeInOutQuart'
            }
        }
    });

    // Add event annotations if events are loaded
    if (appData.events && appData.events.events) {
        addEventAnnotations(appData.chart);
    }
}

// Add event annotations to the chart
function addEventAnnotations(chart) {
    const events = appData.events.events;
    const timezone = appData.events.time_zone || 'UTC';

    // Create annotation plugin configuration
    if (!chart.options.plugins.annotation) {
        chart.options.plugins.annotation = {
            annotations: {}
        };
    }

    events.forEach((event, index) => {
        const eventId = `event-${index}`;
        const eventTime = new Date(event.start_time);
        const eventType = event.event_type || 'event';
        const label = event.label || `${eventType} ${index + 1}`;

        // Determine color based on event type
        let backgroundColor = '#6f42c1'; // default purple
        let borderColor = '#5a2d91';

        if (eventType === 'meal') {
            backgroundColor = '#28a745'; // green
            borderColor = '#1e7e34';
        } else if (eventType === 'exercise') {
            backgroundColor = '#007bff'; // blue
            borderColor = '#0056b3';
        } else if (eventType === 'medication') {
            backgroundColor = '#ffc107'; // yellow
            borderColor = '#d39e00';
        }

        // Add vertical line annotation
        chart.options.plugins.annotation.annotations[eventId] = {
            type: 'line',
            xMin: eventTime,
            xMax: eventTime,
            borderColor: borderColor,
            borderWidth: 2,
            borderDash: [5, 5],
            label: {
                content: label,
                enabled: true,
                position: 'start',
                backgroundColor: backgroundColor,
                color: 'white',
                font: { size: 12, weight: 'bold' }
            }
        };
    });

    chart.update('none'); // Update without animation
}

// Display events in the UI
function displayEvents() {
    if (!appData.events || !appData.events.events) {
        document.getElementById('eventsList').innerHTML = '<p>No events loaded</p>';
        return;
    }

    const eventsList = document.getElementById('eventsList');
    const events = appData.events.events;

    if (events.length === 0) {
        eventsList.innerHTML = '<p>No events in this dataset</p>';
        return;
    }

    const eventsHtml = events.map(event => {
        const eventType = event.event_type || 'event';
        const label = event.label || event.event_id;
        const startTime = new Date(event.start_time).toLocaleString();
        let html = `
            <div class="event-item ${eventType}">
                <div class="event-header">
                    <div class="event-label">${escapeHtml(label)}</div>
                    <div class="event-time">${startTime}</div>
                </div>
        `;

        // Add carb estimate if present
        if (event.exposure_components) {
            const carbs = event.exposure_components.find(comp => comp.name.toLowerCase().includes('carb'));
            if (carbs) {
                html += `<div class="event-carbs">${carbs.value} ${carbs.unit}</div>`;
            }
        }

        // Add annotation quality
        if (event.annotation_quality !== undefined) {
            const quality = Math.round(event.annotation_quality * 100);
            html += `<div class="event-quality">Quality: ${quality}%</div>`;
        }

        // Add context tags if present
        if (event.context_tags && event.context_tags.length > 0) {
            html += `<div style="margin-top: 8px; font-size: 0.85em; color: #666;">Tags: ${event.context_tags.join(', ')}</div>`;
        }

        html += '</div>';
        return html;
    }).join('');

    eventsList.innerHTML = eventsHtml;
}

// Display hypotheses and answerability
function displayHypotheses() {
    if (!appData.hypotheses || !appData.hypotheses.hypotheses) {
        document.getElementById('hypothesesList').innerHTML = '<p>No hypotheses loaded</p>';
        return;
    }

    const hypothesesList = document.getElementById('hypothesesList');
    const hypotheses = appData.hypotheses.hypotheses;

    if (hypotheses.length === 0) {
        hypothesesList.innerHTML = '<p>No hypotheses in this dataset</p>';
        return;
    }

    const hypothesesHtml = hypotheses.map(hypothesis => {
        const answerability = hypothesis.answerability || {};
        const status = answerability.answerable || 'unknown';
        const confidence = answerability.confidence || 0;
        const issues = answerability.issues || [];

        const statusClass = `status-${status}`;
        const statusText = status.charAt(0).toUpperCase() + status.slice(1);

        let html = `
            <div class="hypothesis-item">
                <div class="hypothesis-text">${escapeHtml(hypothesis.text || hypothesis.hypothesis_id)}</div>
                <div class="answerability-status">
                    <div class="status-badge ${statusClass}">${statusText}</div>
                    <div class="confidence-score">
                        <div class="confidence-bar">
                            <div class="confidence-fill confidence-${confidenceLevel(confidence)}" style="width: ${confidence * 100}%"></div>
                        </div>
                        <span style="font-size: 0.85em; color: #666;">${Math.round(confidence * 100)}%</span>
                    </div>
                </div>
        `;

        if (issues.length > 0) {
            html += `
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee;">
                    <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">Issues:</div>
                    <ul style="font-size: 0.85em; color: #856404; margin-left: 20px;">
                        ${issues.map(issue => `<li>${escapeHtml(issue)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        html += '</div>';
        return html;
    }).join('');

    hypothesesList.innerHTML = hypothesesHtml;
}

// Display metrics if available
function displayMetrics() {
    if (!appData.metrics || !appData.metrics.metrics) {
        document.getElementById('metricsContent').innerHTML =
            '<p>No metrics loaded. Upload a metrics file or calculate them using the CLI tool.</p>';
        return;
    }

    const metrics = appData.metrics.metrics;
    const metricsContent = document.getElementById('metricsContent');

    // Group metrics by event
    const metricsByEvent = {};
    metrics.forEach(metric => {
        if (!metricsByEvent[metric.event_id]) {
            metricsByEvent[metric.event_id] = [];
        }
        metricsByEvent[metric.event_id].push(metric);
    });

    // Find corresponding events for labels
    const eventsMap = {};
    if (appData.events && appData.events.events) {
        appData.events.events.forEach(event => {
            eventsMap[event.event_id] = event;
        });
    }

    let html = '';

    Object.entries(metricsByEvent).forEach(([eventId, eventMetrics]) => {
        const event = eventsMap[eventId];
        const eventLabel = event ? event.label || eventId : eventId;

        html += `<h3 style="margin-bottom: 15px; color: #667eea;">${escapeHtml(eventLabel)}</h3>`;
        html += '<div class="metrics-grid">';

        eventMetrics.forEach(metric => {
            const value = metric.value;
            const unit = metric.unit;
            const coverage = metric.quality_summary ? metric.quality_summary.coverage_percentage : 100;
            const hasQualityWarning = coverage && coverage < 70;

            const icon = getMetricIcon(metric.metric_name);
            const title = getMetricTitle(metric.metric_name);

            html += `
                <div class="metric-card" style="${hasQualityWarning ? 'border: 2px solid #ffc107;' : ''}">
                    <h4>${icon} ${title}</h4>
                    <div class="metric-value">
                        ${formatMetricValue(value, metric.metric_name)}
                    </div>
                    <div class="metric-unit">${escapeHtml(unit)}</div>
            `;

            if (coverage !== undefined) {
                html += `<div class="metric-coverage">Coverage: ${Math.round(coverage)}%</div>`;
            }

            if (hasQualityWarning) {
                html += `<div class="metric-coverage" style="color: #ffc107;">⚠️ Low coverage</div>`;
            }

            html += '</div>';
        });

        html += '</div>';
    });

    metricsContent.innerHTML = html;
}

// Helper functions

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function confidenceLevel(confidence) {
    if (confidence >= 0.8) return 'high';
    if (confidence >= 0.5) return 'medium';
    return 'low';
}

function getMetricIcon(metricName) {
    const icons = {
        'baseline_glucose': '🎯',
        'delta_peak': '📈',
        'iAUC': '📊',
        'time_to_peak': '⏱️',
        'recovery_slope': '📉',
        'shape_classification': '👁️'
    };
    return icons[metricName] || '📋';
}

function getMetricTitle(metricName) {
    const titles = {
        'baseline_glucose': 'Baseline Glucose',
        'delta_peak': 'ΔPeak Change',
        'iAUC': 'Incremental AUC',
        'time_to_peak': 'Time to Peak',
        'recovery_slope': 'Recovery Slope',
        'shape_classification': 'Shape Pattern'
    };
    return titles[metricName] || metricName;
}

function formatMetricValue(value, metricName) {
    if (metricName === 'shape_classification') {
        return value;
    }
    if (metricName === 'time_to_peak' || metricName === 'baseline_glucose') {
        return Math.round(value);
    }
    if (metricName === 'delta_peak' || metricName === 'iAUC') {
        return value.toFixed(0);
    }
    return value.toFixed(2);
}

// Export functions for console debugging
window.analyzer = {
    appData,
    visualizeCGM,
    displayEvents,
    displayHypotheses,
    displayMetrics
};
