// BrainBuzz Quiz Game Logic

let quizQuestions = [];
let currentQuestionIndex = 0;
let score = 0;
let buzzPoints = 0;
let buzzSessionId = new URLSearchParams(window.location.search).get('session_id');
let questionStartTime = null;
let firstAnswered = false;
let timerInterval = null;
let timeLeft = 15; // 15 seconds per question
let answerSelected = false;

// DOM Elements
const quizStartBtn = document.getElementById('quizStartBtn');
const quizIntro = document.getElementById('quizIntro');
const quizPlay = document.getElementById('quizPlay');
const quizResults = document.getElementById('quizResults');

const questionNumEl = document.getElementById('questionNum');
const timerValEl = document.getElementById('timerVal');
const progressBar = document.getElementById('progressBar');
const questionTextEl = document.getElementById('questionText');
const optionsGrid = document.getElementById('optionsGrid');

const finalScoreEl = document.getElementById('finalScore');
const pointsAwardedEl = document.getElementById('pointsAwarded');

if (quizStartBtn) {
    quizStartBtn.addEventListener('click', startQuiz);
}

const quizRetryBtn = document.getElementById('quizRetryBtn');
if (quizRetryBtn) {
    quizRetryBtn.addEventListener('click', () => {
        quizResults.classList.add('hidden');
        startQuiz();
    });
}

async function startQuiz() {
    quizIntro.classList.add('hidden');
    quizPlay.classList.remove('hidden');
    
    // Check if difficulty parameter is provided in container dataset
    const level = quizPlay.dataset.level || 'Intermediate';
    
    try {
        const response = await fetch(`/api/quiz/questions?difficulty=${level}`);
        quizQuestions = await response.json();
        
        if (quizQuestions.length === 0) {
            questionTextEl.innerHTML = "<p>No questions found for this level. Please check back later!</p>";
            return;
        }
        
        currentQuestionIndex = 0;
        score = 0;
        showQuestion(quizQuestions[currentQuestionIndex]);
        
    } catch (err) {
        console.error("Failed to load questions", err);
        showToast("Error loading quiz questions", "error");
    }
}

function showQuestion(question) {
    answerSelected = false;
    firstAnswered = false;
    questionStartTime = Date.now();
    timeLeft = 15;
    timerValEl.innerText = timeLeft;
    
    // Update progress
    const qNumber = currentQuestionIndex + 1;
    questionNumEl.innerText = `Question ${qNumber} of ${quizQuestions.length}`;
    progressBar.style.width = `${(qNumber / quizQuestions.length) * 100}%`;
    
    // Render question
    questionTextEl.innerText = question.question_text;
    
    // Render choices
    optionsGrid.innerHTML = '';
    const choices = [
        { key: 'A', text: question.option_a },
        { key: 'B', text: question.option_b },
        { key: 'C', text: question.option_c },
        { key: 'D', text: question.option_d }
    ];
    
    choices.forEach(choice => {
        const btn = document.createElement('button');
        btn.className = 'quiz-option-btn';
        btn.dataset.choice = choice.key;
        btn.innerHTML = `
            <span>${choice.key}. ${choice.text}</span>
            <i class="far fa-circle"></i>
        `;
        btn.addEventListener('click', () => selectAnswer(btn, choice.key, question.correct_option));
        optionsGrid.appendChild(btn);
    });
    
    // Start countdown
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        timeLeft--;
        timerValEl.innerText = timeLeft;
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            timeOut(question.correct_option);
        }
    }, 1000);
}

function selectAnswer(button, selected, correct) {
    if (answerSelected) return;
    answerSelected = true;
    clearInterval(timerInterval);
    
    // Disable all options
    const buttons = optionsGrid.querySelectorAll('.quiz-option-btn');
    buttons.forEach(btn => btn.disabled = true);
    
    // Show correct/incorrect feedback
    const isCorrect = selected === correct;
    let points = 0;

    if (isCorrect) {
        button.classList.add('correct');
        button.querySelector('i').className = 'fas fa-check-circle';

        if (buzzSessionId) {
            points = firstAnswered ? 10 : 15;
            firstAnswered = true;
            buzzPoints += points;
        } else {
            score++;
        }
    } else {
        button.classList.add('incorrect');
        button.querySelector('i').className = 'fas fa-times-circle';
        points = -1;

        // Highlight correct button
        buttons.forEach(btn => {
            if (btn.dataset.choice === correct) {
                btn.classList.add('correct');
                btn.querySelector('i').className = 'fas fa-check-circle';
            }
        });

        if (buzzSessionId) {
            buzzPoints += points;
        }
    }

    if (buzzSessionId) {
        fetch('/api/buzz/respond', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: buzzSessionId,
                question_index: currentQuestionIndex,
                answer: selected,
                is_correct: isCorrect,
                points_earned: Math.max(0, points)
            })
        }).catch(err => {
            console.error('Failed to submit BrainBuzz response', err);
        });
    }
    
    // Delay slightly and load next question
    setTimeout(nextQuestion, 1800);
}

function timeOut(correct) {
    answerSelected = true;
    // Highlight correct option
    const buttons = optionsGrid.querySelectorAll('.quiz-option-btn');
    buttons.forEach(btn => {
        btn.disabled = true;
        if (btn.dataset.choice === correct) {
            btn.classList.add('correct');
            btn.querySelector('i').className = 'fas fa-check-circle';
        }
    });
    
    showToast("Time's Up!", "warning");
    setTimeout(nextQuestion, 1800);
}

function nextQuestion() {
    currentQuestionIndex++;
    if (currentQuestionIndex < quizQuestions.length) {
        showQuestion(quizQuestions[currentQuestionIndex]);
    } else {
        finishQuiz();
    }
}

async function finishQuiz() {
    quizPlay.classList.add('hidden');
    quizResults.classList.remove('hidden');

    if (buzzSessionId) {
        finalScoreEl.innerText = `${buzzPoints} pts`;
        pointsAwardedEl.innerText = `${buzzPoints >= 0 ? '+' : ''}${buzzPoints}`;
        showToast(`BrainBuzz finished! You earned ${buzzPoints} points.`, 'success');
        return;
    }

    finalScoreEl.innerText = `${score} / ${quizQuestions.length}`;
    const pts = score * 10;
    pointsAwardedEl.innerText = `+${pts}`;

    try {
        const response = await fetch('/api/quiz/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ score: score })
        });
        const result = await response.json();
        if (result.success) {
            showToast(`Quiz completed! You earned ${pts} points.`, 'success');
        }
    } catch (err) {
        console.error("Failed to submit score", err);
        showToast("Error updating scores", "error");
    }
}
