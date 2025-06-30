let intervalId = null;

function submitRecipe() {
    document.getElementById('section3').style.backgroundImage = '';
    document.getElementById('section3').style.background = '#487b7f';
    document.getElementById('tick1').classList.remove('hidden');

    var field = document.getElementById('recipe');
    var button = document.getElementById('submit-recipe');

    if (field) field.style.display = 'none';
    if (button) button.style.display = 'none';

    $.ajax({
        type: 'POST',
        url: '/submit',
        data: $('#recipe-form').serialize(),
        success: function() {
            setTimeout(() => {
                window.location.href = '/loading';
            }, 500);
        },
        error: function(xhr, status, error) {
            console.error('Submit failed:', error);
            alert('Failed to submit recipe. Please try again.');
            if (field) field.style.display = 'block';
            if (button) button.style.display = 'block';
        }
    });
}

function submitZip() {
    var field = document.getElementById('zip');
    var button = document.getElementById('zip-submit');
    var zipCode = field.value;

    if (!isValidUSZip(zipCode)) {
        alert("Invalid ZIP! Please enter a valid US ZIP code.");
        return false;
    }

    document.getElementById('section2').style.backgroundImage = '';
    document.getElementById('section2').style.background = '#364851';
    document.getElementById('tick2').classList.remove('hidden');
    document.getElementById('section3').classList.add('visible');

    if (field) field.style.display = 'none';
    if (button) button.style.display = 'none';

    return true;
}

function isValidUSZip(sZip) {
    return /^\d{5}(-\d{4})?$/.test(sZip);
}

function checkResults() {
    console.log("Polling /check_results...");
    $.ajax({
        type: 'GET',
        url: '/check_results',
        success: function(data) {
            if (data.status === 'ready') {
                console.log("Redirecting to /results...");
                if (intervalId) {
                    clearInterval(intervalId); // ✅ now visible
                    intervalId = null;
                }
                window.location.href = '/results';
            } else {
                var progress = data.progress || { total: 1, completed: 0 };
                var percentage = Math.round((progress.completed / progress.total) * 100);
                var progressBar = document.getElementById('progress-bar');
                var progressText = document.getElementById('progress-text');
                if (progressBar) {
                    progressBar.style.width = percentage + '%';
                }
                if (progressText) {
                    progressText.innerText = `Processed ${progress.completed} of ${progress.total} ingredients (${percentage}%)`;
                }
            }
        },
        error: function(xhr, status, error) {
            console.error('Check results failed:', error);
        }
    });
}

if (window.location.pathname === '/loading') {
    function startPolling() {
        checkResults();
        intervalId = setInterval(checkResults, 15000);
    }

    $.getJSON('/check_results', function(data) {
        if (data.status !== 'waiting') {
            startPolling();
        } else {
            console.log("Waiting for form submission...");
            setTimeout(startPolling, 3000);
        }
    });
}
