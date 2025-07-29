class InterviewApp {
    constructor() {
        this.websocket = null;
        this.proctoringWebSocket = null;
        this.proctoringSessionId = null;
        this.audioContext = null;
        this.mediaRecorder = null;
        this.mediaStream = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.avatar = "default.png";
        this.inactivityTimer = null;
        this.INACTIVITY_TIMEOUT = 15000;
        this.isWaitingForResponse = false;
        this.interimTranscript = '';
        this.finalTranscript = '';
        this.recognition = null;
        this.isEditing = false;
        this.liveTranscriptElement = null;
        this.websocketIsAlive = false;
        this.currentQuestionNumber = 1;
        this.isPlayingAudio = false;
        this.isProcessingQuestion = false;
        this.interviewEnded = false;
        this.currentEvaluationScore = 0;
        this.totalEvaluations = 0;
        this.averageScore = 0;
        
        // ADDED: Face capture system
        this.captureVideo = null;
        this.captureCanvas = null;
        this.captureContext = null;
        this.capturedImageData = null;
        this.faceCaptureDone = false;
        
        // ORIGINAL WORKING: Proctoring system
        this.proctoring = new PythonProctoringSystem();
        
        this.initElements();
        this.initEventListeners();
        this.initQuestionLog();
        this.initFaceCapture(); // ADDED
    }

    initQuestionLog() {
        console.log("Interview question logging initialized");
    }

    logQuestion(question) {
        const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
        const logEntry = {
            timestamp: timestamp,
            questionNumber: this.currentQuestionNumber,
            question: question
        };
        console.log(`[${timestamp}] Question ${this.currentQuestionNumber}: "${question}"`);
        this.currentQuestionNumber += 1;
    }

    initElements() {
        // ORIGINAL WORKING ELEMENTS
        this.elements = {
            startBtn: document.getElementById('start-interview-btn'),
            uploadForm: document.getElementById('upload-form'),
            resumeInput: document.getElementById('resume'),
            avatarSelect: document.getElementById('avatar'),
            interviewContainer: document.getElementById('interview-container'),
            transcriptContainer: document.getElementById('transcript-container'),
            recordBtn: document.getElementById('record-btn'),
            sendTextBtn: document.getElementById('send-text-btn'),
            userTextInput: document.getElementById('user-text-input'),
            statusIndicator: document.getElementById('status-indicator'),
            audioPlayer: document.getElementById('audio-player'),
            interviewerAvatar: document.getElementById('interviewer-avatar'),
            endInterviewBtn: document.createElement('button'),
            loadingIndicator: document.createElement('div'),
            editControls: document.createElement('div'),
            editTextarea: document.createElement('textarea'),
            confirmEditBtn: document.createElement('button'),
            cancelEditBtn: document.createElement('button'),
            scoreDisplay: document.createElement('div')
        };

        // ORIGINAL WORKING: End Interview Button
        this.elements.endInterviewBtn.id = 'end-interview-btn';
        this.elements.endInterviewBtn.textContent = 'End Interview';
        this.elements.endInterviewBtn.className = 'btn-end-interview';
        this.elements.interviewContainer.appendChild(this.elements.endInterviewBtn);

        // ORIGINAL WORKING: Loading Indicator
        this.elements.loadingIndicator.className = 'loading-indicator';
        this.elements.loadingIndicator.innerHTML = '<div class="spinner"></div>Processing your response...';
        this.elements.loadingIndicator.style.display = 'none';
        this.elements.interviewContainer.appendChild(this.elements.loadingIndicator);

        // ORIGINAL WORKING: Score Display
        this.elements.scoreDisplay.className = 'score-display';
        this.elements.scoreDisplay.innerHTML = `
            <div class="score-header">
                <h3>Performance Tracker</h3>
            </div>
            <div class="score-content">
                <div class="current-average">Average Score: <span id="average-score">0.0</span>/10</div>
                <div class="questions-answered">Questions Answered: <span id="questions-count">0</span></div>
            </div>
        `;
        this.elements.scoreDisplay.style.display = 'none';
        this.elements.interviewContainer.appendChild(this.elements.scoreDisplay);

        // ORIGINAL WORKING: Edit Controls
        this.elements.editControls.className = 'edit-controls';
        this.elements.editControls.style.display = 'none';
        this.elements.editTextarea.className = 'edit-textarea';
        this.elements.editTextarea.placeholder = 'Edit your response...';
        this.elements.confirmEditBtn.textContent = 'Send';
        this.elements.confirmEditBtn.className = 'btn-confirm-edit';
        this.elements.cancelEditBtn.textContent = 'Cancel';
        this.elements.cancelEditBtn.className = 'btn-cancel-edit';
        
        this.elements.editControls.appendChild(this.elements.editTextarea);
        this.elements.editControls.appendChild(this.elements.confirmEditBtn);
        this.elements.editControls.appendChild(this.elements.cancelEditBtn);
        this.elements.interviewContainer.appendChild(this.elements.editControls);
    }

    // ADDED: Face capture initialization
    initFaceCapture() {
        this.captureVideo = document.getElementById('capture-video');
        this.captureCanvas = document.getElementById('capture-canvas');
        if (this.captureCanvas) {
            this.captureContext = this.captureCanvas.getContext('2d');
        }
    }

    initEventListeners() {
        // ORIGINAL WORKING EVENT LISTENERS
        this.elements.startBtn.addEventListener('click', () => this.startInterview());
        this.elements.recordBtn.addEventListener('click', () => this.toggleRecording());
        this.elements.sendTextBtn.addEventListener('click', () => this.sendTextResponse());
        this.elements.userTextInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendTextResponse();
            }
        });
        this.elements.endInterviewBtn.addEventListener('click', () => this.endInterviewManually());

        // Edit controls
        this.elements.confirmEditBtn.addEventListener('click', () => this.confirmEdit());
        this.elements.cancelEditBtn.addEventListener('click', () => this.cancelEdit());

        // ADDED: Face capture controls
        const captureBtn = document.getElementById('capture-photo-btn');
        const retakeBtn = document.getElementById('retake-photo-btn');
        const proceedBtn = document.getElementById('proceed-interview-btn');
        
        if (captureBtn) captureBtn.addEventListener('click', () => this.capturePhoto());
        if (retakeBtn) retakeBtn.addEventListener('click', () => this.retakePhoto());
        if (proceedBtn) proceedBtn.addEventListener('click', () => this.proceedToInterview());
    }

    async startInterview() {
        // ADDED: Validate user details first
        const name = document.getElementById('user-name').value.trim();
        const phone = document.getElementById('user-phone').value.trim();
        const email = document.getElementById('user-email').value.trim();
        
        if (!name || !phone || !email) {
            alert('Please fill in all personal information fields.');
            return;
        }
        
        const formData = new FormData();
        const resumeFiles = document.getElementById('resume').files;
        
        if (!resumeFiles || resumeFiles.length === 0) {
            alert('Please upload your resume.');
            return;
        }
        
        // Add user details to form data
        formData.append('name', name);
        formData.append('phone', phone);
        formData.append('email', email);
        
        // Add resume files
        for (let i = 0; i < resumeFiles.length; i++) {
            formData.append('resume', resumeFiles[i]);
        }
        
        try {
            this.showStatus("Processing your information...", "processing");
            const response = await fetch('/start_interview', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            
            if (response.ok && data.status === 'ready_for_face_capture') {
                this.proctoringSessionId = data.proctoring_session_id;
                this.showStatus("Please proceed to face verification", "processing");
                
                // Hide form and show face capture
                const userDetailsForm = document.getElementById('user-details-form');
                if (userDetailsForm) userDetailsForm.style.display = 'none';
                this.elements.uploadForm.style.display = 'none';
                
                const faceCaptureContainer = document.getElementById('face-capture-container');
                if (faceCaptureContainer) {
                    faceCaptureContainer.style.display = 'block';
                    // Initialize camera for face capture
                    await this.initializeCamera();
                } else {
                    // Fallback: Skip face capture if container not found
                    console.warn("Face capture container not found, skipping to interview");
                    this.skipToInterview();
                }
            } else {
                throw new Error(data.detail || "Failed to start interview");
            }
        } catch (error) {
            console.error("Error starting interview:", error);
            this.showStatus(`Error: ${error.message}`, "error");
        }
    }

    // ADDED: Skip face capture fallback
    async skipToInterview() {
        try {
            // Send dummy image data to activate session
            const dummyImage = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAAAAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwDVAA==";
            
            const response = await fetch('/capture_reference_face', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    image_data: dummyImage
                })
            });

            if (response.ok) {
                const sessionResponse = await fetch('/start_interview_session', {
                    method: 'POST'
                });
                
                if (sessionResponse.ok) {
                    this.proceedDirectlyToInterview();
                }
            }
        } catch (error) {
            console.error("Error in fallback:", error);
            this.proceedDirectlyToInterview();
        }
    }

    // ADDED: Initialize camera for face capture
    async initializeCamera() {
        try {
            this.showStatus("Requesting camera access...", "processing");
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { 
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user'
                }
            });
            this.captureVideo.srcObject = stream;
            
            // Wait for video to load
            await new Promise((resolve) => {
                this.captureVideo.addEventListener('loadedmetadata', resolve, { once: true });
            });
            
            this.showStatus("Camera ready - capture your photo", "active");
        } catch (error) {
            console.error("Error accessing camera:", error);
            this.showStatus("Camera access denied. Proceeding without face verification...", "warning");
            // Fallback: Skip face capture
            setTimeout(() => this.skipToInterview(), 2000);
        }
    }

    // ADDED: Capture photo
    capturePhoto() {
        try {
            if (!this.captureVideo || !this.captureVideo.videoWidth || !this.captureVideo.videoHeight) {
                throw new Error("Video not ready. Please wait for camera to initialize.");
            }

            // Set canvas dimensions to match video
            this.captureCanvas.width = this.captureVideo.videoWidth;
            this.captureCanvas.height = this.captureVideo.videoHeight;
            
            // Draw current frame to canvas
            this.captureContext.drawImage(
                this.captureVideo, 
                0, 0, 
                this.captureCanvas.width, 
                this.captureCanvas.height
            );
            
            // Get image data
            this.capturedImageData = this.captureCanvas.toDataURL('image/jpeg', 0.8);
            
            // Show preview
            const capturedPhoto = document.getElementById('captured-photo');
            if (capturedPhoto) {
                capturedPhoto.src = this.capturedImageData;
                const preview = document.querySelector('.captured-photo-preview');
                if (preview) preview.style.display = 'block';
            }
            
            // Update controls
            const captureBtn = document.getElementById('capture-photo-btn');
            const retakeBtn = document.getElementById('retake-photo-btn');
            const proceedBtn = document.getElementById('proceed-interview-btn');
            
            if (captureBtn) captureBtn.style.display = 'none';
            if (retakeBtn) retakeBtn.style.display = 'inline-block';
            if (proceedBtn) proceedBtn.style.display = 'inline-block';
            
            this.showStatus("Photo captured! Review and proceed", "success");
        } catch (error) {
            console.error("Error capturing photo:", error);
            this.showStatus(`Failed to capture photo: ${error.message}`, "error");
        }
    }

    // ADDED: Retake photo
    retakePhoto() {
        // Reset controls
        const captureBtn = document.getElementById('capture-photo-btn');
        const retakeBtn = document.getElementById('retake-photo-btn');
        const proceedBtn = document.getElementById('proceed-interview-btn');
        const preview = document.querySelector('.captured-photo-preview');
        
        if (captureBtn) captureBtn.style.display = 'inline-block';
        if (retakeBtn) retakeBtn.style.display = 'none';
        if (proceedBtn) proceedBtn.style.display = 'none';
        if (preview) preview.style.display = 'none';
        
        this.capturedImageData = null;
        this.showStatus("Camera ready - capture your photo", "active");
    }

    // ADDED: Proceed to interview after face capture
    async proceedToInterview() {
        if (!this.capturedImageData) {
            this.showStatus('Please capture your photo first.', 'error');
            return;
        }

        try {
            this.showStatus("Verifying your identity...", "processing");
            
            // Send captured face to backend
            const response = await fetch('/capture_reference_face', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    image_data: this.capturedImageData
                })
            });

            const result = await response.json();
            
            if (response.ok && result.status === 'success') {
                // Start interview session
                const sessionResponse = await fetch('/start_interview_session', {
                    method: 'POST'
                });
                
                if (sessionResponse.ok) {
                    this.proceedDirectlyToInterview();
                } else {
                    throw new Error("Failed to start interview session");
                }
            } else {
                throw new Error(result.message || "Failed to verify identity");
            }
        } catch (error) {
            console.error("Error proceeding to interview:", error);
            this.showStatus(`Error: ${error.message}`, "error");
            // Fallback: Proceed anyway after a delay
            setTimeout(() => {
                if (confirm("Would you like to proceed without face verification?")) {
                    this.proceedDirectlyToInterview();
                }
            }, 2000);
        }
    }

    // ADDED: Proceed directly to interview
    proceedDirectlyToInterview() {
        this.faceCaptureDone = true;
        
        // Hide face capture
        const faceContainer = document.getElementById('face-capture-container');
        if (faceContainer) faceContainer.style.display = 'none';
        
        // Show interview container
        this.elements.interviewContainer.style.display = 'block';
        this.elements.scoreDisplay.style.display = 'block';
        
        // Stop capture camera stream
        if (this.captureVideo && this.captureVideo.srcObject) {
            const tracks = this.captureVideo.srcObject.getTracks();
            tracks.forEach(track => track.stop());
        }
        
        // Initialize proctoring system and connect WebSocket
        this.proctoring.initialize(this.proctoringSessionId).then(() => {
            this.connectWebSocket();
        });
    }

    connectWebSocket() {
        // ORIGINAL WORKING WEBSOCKET CODE
        this.websocket = new WebSocket(`ws://${window.location.host}/ws/interview`);
        this.websocketIsAlive = true;

        this.websocket.onopen = () => {
            console.log("WebSocket connected");
            this.showStatus("Interview started", "active");
        };

        this.websocket.onmessage = async (event) => {
            if (!this.websocketIsAlive) return;

            try {
                const data = JSON.parse(event.data);
                console.log("Received WebSocket message:", data.type);

                if (data.type === 'question' && this.isProcessingQuestion) {
                    console.log("Already processing a question, ignoring duplicate");
                    return;
                }

                switch (data.type) {
                    case 'question':
                        await this.handleQuestion(data);
                        break;
                    case 'answer_evaluation':
                        this.displayEvaluationFeedback(data);
                        break;
                    case 'processing_response':
                        this.showStatus(data.content, "processing");
                        break;
                    case 'evaluation_error':
                        this.showStatus(data.content, "warning");
                        break;
                    case 'transcription':
                        this.addToTranscript('You', data.content);
                        this.resetInactivityTimer();
                        break;
                    case 'interview_concluded':
                        await this.handleInterviewConclusion(data);
                        break;
                    case 'processing_question':
                        this.showLoading();
                        break;
                    case 'error':
                        this.showStatus(data.content, "error");
                        this.stopRecording();
                        this.isProcessingQuestion = false;
                        break;
                }
            } catch (e) {
                console.error("Error processing WebSocket message:", e);
                this.isProcessingQuestion = false;
            }
        };

        this.websocket.onclose = () => {
            console.log("WebSocket disconnected");
            this.websocketIsAlive = false;
            this.clearInactivityTimer();
            if (this.isRecording) {
                this.stopRecording();
            }
            if (!this.isEditing && !this.interviewEnded) {
                this.showStatus("Connection lost. Please refresh the page.", "error");
            }
        };

        this.websocket.onerror = (error) => {
            console.error("WebSocket error:", error);
            this.websocketIsAlive = false;
            this.showStatus("Connection error", "error");
        };
    }

    // ALL FOLLOWING METHODS ARE ORIGINAL WORKING CODE

    async handleQuestion(data) {
        this.isProcessingQuestion = true;
        this.isWaitingForResponse = false;
        this.hideLoading();

        if (this.isRecording) {
            this.stopRecording();
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        this.addToTranscript('Interviewer', data.content);
        this.logQuestion(data.content);

        if (data.audio_file) {
            await this.playAudio(data.audio_file);
        }

        if (data.start_recording) {
            await this.startRecording();
        } else if (data.stop_recording) {
            this.stopRecording();
        }

        this.isProcessingQuestion = false;
    }

    async handleInterviewConclusion(data) {
        this.addToTranscript('Interviewer', data.content);
        
        if (data.audio_file) {
            await this.playAudio(data.audio_file);
        }
        
        this.stopRecording();
        await this.endInterview();

        if (data.final_average_score !== undefined) {
            this.updateScoreDisplay(data.final_average_score, data.total_questions || 0);
        }

        setTimeout(() => {
            window.location.href = '/report';
        }, 3000);
    }

    displayEvaluationFeedback(evaluation) {
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'evaluation-feedback';
        feedbackDiv.innerHTML = `
            <div class="evaluation-header">
                <h4>🤖 AI Evaluation</h4>
                <span class="score-badge">Overall: ${evaluation.overall_score}/10</span>
            </div>
            <div class="score-breakdown">
                <div class="score-item">
                    <span class="score-label">Technical Accuracy:</span>
                    <span class="score-value">${evaluation.technical_accuracy}/10</span>
                </div>
                <div class="score-item">
                    <span class="score-label">Communication:</span>
                    <span class="score-value">${evaluation.communication_clarity}/10</span>
                </div>
                <div class="score-item">
                    <span class="score-label">Relevance:</span>
                    <span class="score-value">${evaluation.relevance}/10</span>
                </div>
                <div class="score-item">
                    <span class="score-label">Depth:</span>
                    <span class="score-value">${evaluation.depth}/10</span>
                </div>
            </div>
            <div class="evaluation-content">
                <div class="feedback-section">
                    <strong>💡 Feedback:</strong> ${evaluation.feedback}
                </div>
                <div class="strengths-section">
                    <strong>✅ Strengths:</strong> ${evaluation.strengths}
                </div>
                <div class="weaknesses-section">
                    <strong>📈 Areas for Improvement:</strong> ${evaluation.weaknesses}
                </div>
                <div class="running-average">
                    <strong>📊 Running Average:</strong> ${evaluation.average_score}/10 
                    (${evaluation.total_questions_answered} questions answered)
                </div>
            </div>
        `;
        
        this.elements.transcriptContainer.appendChild(feedbackDiv);
        this.elements.transcriptContainer.scrollTop = this.elements.transcriptContainer.scrollHeight;

        this.updateScoreDisplay(evaluation.average_score, evaluation.total_questions_answered);
    }

    updateScoreDisplay(averageScore, questionsAnswered) {
        const avgScoreElement = document.getElementById('average-score');
        const questionsCountElement = document.getElementById('questions-count');
        
        if (avgScoreElement) {
            avgScoreElement.textContent = averageScore.toFixed(1);
        }
        if (questionsCountElement) {
            questionsCountElement.textContent = questionsAnswered;
        }

        const scoreDisplay = this.elements.scoreDisplay;
        scoreDisplay.className = 'score-display';
        if (averageScore >= 8) {
            scoreDisplay.classList.add('excellent');
        } else if (averageScore >= 6) {
            scoreDisplay.classList.add('good');
        } else if (averageScore >= 4) {
            scoreDisplay.classList.add('fair');
        } else {
            scoreDisplay.classList.add('needs-improvement');
        }
    }

    resetInactivityTimer() {
        this.clearInactivityTimer();
        this.inactivityTimer = setTimeout(() => {
            if (this.isRecording) {
                this.stopRecording();
                this.showStatus("No response detected, please try again", "warning");
                
                setTimeout(() => {
                    if (this.websocket && this.websocketIsAlive && this.websocket.readyState === WebSocket.OPEN) {
                        this.showStatus("Please provide your response", "active");
                        this.startRecording();
                    }
                }, 2000);
            }
        }, this.INACTIVITY_TIMEOUT);
    }

    clearInactivityTimer() {
        if (this.inactivityTimer) {
            clearTimeout(this.inactivityTimer);
            this.inactivityTimer = null;
        }
    }

    async toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            if (this.isPlayingAudio) {
                this.showStatus("Please wait for the question to finish playing", "warning");
                return;
            }
            await this.startRecording();
        }
    }

    async startRecording() {
        if (this.isPlayingAudio) {
            return;
        }

        try {
            this.interimTranscript = '';
            this.finalTranscript = '';

            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = true;
            this.recognition.interimResults = true;

            this.recognition.onresult = (event) => {
                this.resetInactivityTimer();
                this.interimTranscript = '';
                
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        this.finalTranscript += transcript + ' ';
                    } else {
                        this.interimTranscript += transcript;
                    }
                }
                
                this.updateLiveTranscript();

                if (this.finalTranscript.trim().length > 3) {
                    this.resetInactivityTimer();
                }
            };

            this.recognition.onerror = (event) => {
                console.error('Speech recognition error', event.error);
                this.showStatus(`Speech recognition error: ${event.error}`, "error");
            };

            this.recognition.onend = () => {
                if (this.isRecording) {
                    this.recognition.start();
                }
            };

            this.recognition.start();
            this.isRecording = true;
            this.elements.recordBtn.textContent = "🛑";
            this.elements.recordBtn.classList.add('recording');
            this.showStatus("Recording... Speak now", "active");
            this.resetInactivityTimer();

            this.liveTranscriptElement = document.createElement('div');
            this.liveTranscriptElement.className = 'transcript-message you live-transcript';
            this.elements.transcriptContainer.appendChild(this.liveTranscriptElement);

        } catch (error) {
            console.error("Error starting recording:", error);
            this.showStatus("Error starting recording", "error");
        }
    }

    stopRecording() {
        if (this.recognition) {
            this.recognition.stop();
            this.recognition = null;
        }

        this.isRecording = false;
        this.elements.recordBtn.textContent = "🎤";
        this.elements.recordBtn.classList.remove('recording');
        this.clearInactivityTimer();

        if (this.finalTranscript.trim() && this.finalTranscript.trim().length > 3) {
            this.sendResponse(this.finalTranscript.trim());
        }

        if (this.liveTranscriptElement) {
            this.liveTranscriptElement.remove();
            this.liveTranscriptElement = null;
        }
    }

    updateLiveTranscript() {
        if (this.liveTranscriptElement) {
            const fullTranscript = this.finalTranscript + this.interimTranscript;
            this.liveTranscriptElement.innerHTML = `
                <div class="message-content">
                    <strong>You:</strong> ${fullTranscript}
                    <span class="live-indicator">●</span>
                </div>
            `;
            this.elements.transcriptContainer.scrollTop = this.elements.transcriptContainer.scrollHeight;
        }
    }

    sendTextResponse() {
        const text = this.elements.userTextInput.value.trim();
        if (text) {
            this.sendResponse(text);
            this.elements.userTextInput.value = '';
        }
    }

    sendResponse(text) {
        if (!text || text.trim().length < 3) {
            this.showStatus("Please provide a more detailed response", "warning");
            return;
        }

        if (this.websocket && this.websocketIsAlive && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: 'text_response',
                content: text.trim()
            }));
            this.isWaitingForResponse = true;
            this.showLoading();
            this.addToTranscript('You', text);
        }
    }

    addToTranscript(speaker, message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `transcript-message ${speaker.toLowerCase()}`;
        
        const timestamp = new Date().toLocaleTimeString();
        messageDiv.innerHTML = `
            <div class="message-content">
                <strong>${speaker}:</strong> ${message}
                <span class="timestamp">${timestamp}</span>
                ${speaker === 'You' ? '<button class="edit-btn" onclick="app.editMessage(this)">✏️</button>' : ''}
            </div>
        `;
        
        this.elements.transcriptContainer.appendChild(messageDiv);
        this.elements.transcriptContainer.scrollTop = this.elements.transcriptContainer.scrollHeight;
    }

    editMessage(button) {
        const messageDiv = button.closest('.transcript-message');
        const messageContent = messageDiv.querySelector('.message-content');
        const originalText = messageContent.textContent.replace(/^You:\s*/, '').replace(/\d{1,2}:\d{2}:\d{2}\s*(AM|PM)\s*✏️$/, '').trim();
        
        this.elements.editTextarea.value = originalText;
        this.elements.editControls.style.display = 'block';
        this.isEditing = true;
        this.currentEditingMessage = messageDiv;
    }

    confirmEdit() {
        const newText = this.elements.editTextarea.value.trim();
        if (newText && newText.length > 3) {
            const messageContent = this.currentEditingMessage.querySelector('.message-content');
            const timestamp = new Date().toLocaleTimeString();
            messageContent.innerHTML = `
                <strong>You:</strong> ${newText}
                <span class="timestamp">${timestamp} (edited)</span>
                <button class="edit-btn" onclick="app.editMessage(this)">✏️</button>
            `;
            
            this.sendResponse(newText);
        }
        this.cancelEdit();
    }

    cancelEdit() {
        this.elements.editControls.style.display = 'none';
        this.elements.editTextarea.value = '';
        this.isEditing = false;
        this.currentEditingMessage = null;
    }

    async playAudio(filename) {
        try {
            this.isPlayingAudio = true;
            this.elements.audioPlayer.src = `/audio/${filename}`;
            
            const aiAvatar = document.getElementById('interviewer-avatar');
            const aiIndicator = document.querySelector('.ai-avatar-box .speaking-indicator');
            
            if (aiAvatar) {
                aiAvatar.classList.add('ai-speaking', 'blinking');
            }
            if (aiIndicator) {
                aiIndicator.classList.add('ai-speaking');
            }

            await new Promise((resolve, reject) => {
                this.elements.audioPlayer.onended = () => {
                    this.isPlayingAudio = false;
                    
                    if (aiAvatar) {
                        aiAvatar.classList.remove('ai-speaking', 'blinking');
                    }
                    if (aiIndicator) {
                        aiIndicator.classList.remove('ai-speaking');
                    }
                    
                    resolve();
                };
                this.elements.audioPlayer.onerror = reject;
                this.elements.audioPlayer.play();
            });
        } catch (error) {
            console.error("Error playing audio:", error);
            this.isPlayingAudio = false;
        }
    }

    showLoading() {
        this.elements.loadingIndicator.style.display = 'block';
    }

    hideLoading() {
        this.elements.loadingIndicator.style.display = 'none';
    }

    showStatus(message, type) {
        this.elements.statusIndicator.textContent = message;
        this.elements.statusIndicator.className = `status ${type}`;
        
        if (type !== 'error') {
            setTimeout(() => {
                if (this.elements.statusIndicator.textContent === message) {
                    this.elements.statusIndicator.textContent = '';
                    this.elements.statusIndicator.className = 'status';
                }
            }, 5000);
        }
    }

    endInterviewManually() {
        if (this.websocket && this.websocketIsAlive && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: 'end_interview'
            }));
        }
    }

    async endInterview() {
        this.interviewEnded = true;
        this.stopRecording();
        this.clearInactivityTimer();
        
        // Stop proctoring
        this.proctoring.stop();
        
        if (this.websocket) {
            this.websocket.close();
        }
        
        this.showStatus("Interview completed! Generating report...", "success");
        this.elements.endInterviewBtn.style.display = 'none';
        this.elements.recordBtn.disabled = true;
        this.elements.sendTextBtn.disabled = true;
        this.elements.userTextInput.disabled = true;
    }
}

// ORIGINAL WORKING PROCTORING SYSTEM + Face matching capability
class PythonProctoringSystem {
    constructor() {
        this.websocket = null;
        this.sessionId = null;
        this.isActive = false;
        this.sessionActive = true;
        this.initElements();
    }

    initElements() {
        this.video = document.getElementById('student-video');
        this.canvas = document.getElementById('face-canvas');
        if (this.canvas) {
            this.ctx = this.canvas.getContext('2d');
            this.canvas.style.display = 'none';
        }
        
        this.statusElements = {
            warningCount: document.getElementById('warning-count'),
            gazeDirection: document.getElementById('gaze-direction'),
            warningMessage: document.getElementById('warning-message'),
            warningTimer: document.getElementById('warning-timer'),
            proctorWarnings: document.getElementById('proctor-warnings')
        };
    }

    async initialize(sessionId) {
        try {
            this.sessionId = sessionId;
            const stream = await navigator.mediaDevices.getUserMedia({ 
                video: { width: 640, height: 480 } 
            });
            this.video.srcObject = stream;
            this.connectWebSocket();
            this.video.addEventListener('loadeddata', () => {
                if (this.canvas) {
                    this.canvas.width = this.video.videoWidth;
                    this.canvas.height = this.video.videoHeight;
                }
                this.startProcessing();
            });
            this.isActive = true;
            console.log("Python proctoring system initialized");
        } catch (error) {
            console.error("Error initializing Python proctoring system:", error);
        }
    }

    connectWebSocket() {
        this.websocket = new WebSocket(`ws://${window.location.host}/ws/proctoring`);
        this.websocket.onopen = () => {
            console.log("Proctoring WebSocket connected");
        };
        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleProctoringResponse(data);
        };
        this.websocket.onclose = () => console.log("Proctoring WebSocket disconnected");
        this.websocket.onerror = (error) => console.error("Proctoring WebSocket error:", error);
    }

    startProcessing() {
        const processFrame = () => {
            if (!this.isActive || !this.sessionActive) return;
            if (this.video.readyState >= 2 && this.canvas && this.ctx) {
                this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
                const imageData = this.canvas.toDataURL('image/jpeg', 0.8);
                if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                    this.websocket.send(JSON.stringify({
                        type: 'process_frame',
                        session_id: this.sessionId,
                        image_data: imageData
                    }));
                }
            }
            if (this.sessionActive) {
                setTimeout(processFrame, 100);
            }
        };
        processFrame();
    }
handleProctoringResponse(data) {
    try {
        if (data.type === 'reference_face_response') {
            const result = data.result;
            if (result.status === 'success') {
                console.log("Reference face processed successfully");
            } else {
                console.warn("Failed to process reference face:", result.message);
            }
        } else if (data.type === 'proctoring_result') {
            const result = data.result;
            if (result.status === 'success') {
                // Update display elements
                this.updateGazeDisplay(result.gaze_direction || 'UNKNOWN');
                this.updateWarningCount(result.violation_count || 0, result.max_violations || 3);
                
                // FIXED: Handle violations OR hide warnings if none
                if (result.violations && result.violations.length > 0) {
                    this.handleViolations(result.violations);
                } else {
                    // FIXED: No violations - immediately hide warnings
                    this.hideWarning();
                }
                
                // Check if session should be terminated
                if (!result.session_active) {
                    this.terminateSession();
                }
            } else {
                console.warn("Proctoring result error:", result.message);
            }
        } else if (data.type === 'error') {
            console.error("Proctoring error:", data.message);
        }
    } catch (error) {
        console.error("Error handling proctoring response:", error);
    }
}

   handleViolations(violations) {
    let hasActiveWarnings = false;
    
    violations.forEach(violation => {
        console.log("Proctoring violation:", violation.type, violation.message);
        
        if (violation.type === 'warning') {
            this.showWarning(violation.message, violation.timer || '');
            hasActiveWarnings = true;
        } else if (violation.type === 'violation') {
            this.addViolationEffect();
            console.warn(`VIOLATION RECORDED: ${violation.message}`);
        } else if (violation.type === 'session_terminated') {
            this.terminateSession();
        }
    });
    
    // FIXED: Hide warnings immediately if no active warnings
    if (!hasActiveWarnings) {
        this.hideWarning();
    }
}

    addViolationEffect() {
        const cameraBox = document.querySelector('.student-camera-box');
        if (cameraBox) {
            cameraBox.classList.add('violation');
            setTimeout(() => cameraBox.classList.remove('violation'), 2000);
        }
    }

    terminateSession() {
        this.sessionActive = false;
        this.isActive = false;
        this.showWarning('SESSION TERMINATED', 'Too many violations detected!');
        if (this.statusElements.proctorWarnings) {
            this.statusElements.proctorWarnings.style.background = 'rgba(139, 0, 0, 0.95)';
        }
        console.log("SESSION TERMINATED: Too many violations detected!");
        setTimeout(() => {
            window.location.href = '/report';
        }, 3000);
    }

    showWarning(message, timer) {
        if (this.statusElements.warningMessage) {
            this.statusElements.warningMessage.textContent = message;
        }
        if (this.statusElements.warningTimer) {
            this.statusElements.warningTimer.textContent = timer;
        }
        if (this.statusElements.proctorWarnings) {
            this.statusElements.proctorWarnings.classList.add('show');
        }
    }

    hideWarning() {
        if (this.statusElements.proctorWarnings) {
            this.statusElements.proctorWarnings.classList.remove('show');
        }
    }

    updateGazeDisplay(direction) {
        if (this.statusElements.gazeDirection) {
            this.statusElements.gazeDirection.textContent = direction;
        }
    }

    updateWarningCount(current, max) {
        if (this.statusElements.warningCount) {
            this.statusElements.warningCount.textContent = `${current}/${max}`;
        }
    }

    stop() {
        this.isActive = false;
        this.sessionActive = false;
        if (this.video && this.video.srcObject) {
            const tracks = this.video.srcObject.getTracks();
            tracks.forEach(track => track.stop());
        }
        if (this.websocket) {
            this.websocket.close();
        }
        console.log("Python proctoring system stopped");
    }
}

// Initialize the app when the page loads
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new InterviewApp();
});