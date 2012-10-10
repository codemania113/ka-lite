function updateStreakBar() {
    // update the streak bar UI
    $("#streakbar .progress-bar").css("width", exerciseData.percentCompleted + "%");
    if (exerciseData.percentCompleted >= 100) {
        $("#streakbar .progress-bar").addClass("completed");
    }
}

function updatePercentCompleted(correct) {

    if (exerciseData.percentCompleted === 100) {
        return;
    }

    // update the streak; increment by 10 if correct, otherwise reset to 0
    if (correct && !exerciseData.hintUsed) {
        exerciseData.percentCompleted += 10;
    } else {
        exerciseData.percentCompleted = 0;
    }

    // max out at the percentage completed at 100%
    exerciseData.percentCompleted = Math.min(exerciseData.percentCompleted, 100);

    updateStreakBar();

    var data = {
        exercise: exerciseData.exerciseModel.name,
        percentCompleted: exerciseData.percentCompleted
    };

    doRequest("/api/exercises/attempt", data, "POST");

};

$(function() {
    $(Exercises).trigger("problemTemplateRendered");
    $(Exercises).trigger("readyForNextProblem", {userExercise: exerciseData});
    $(Khan).bind("checkAnswer", function(ev, data) {
        updatePercentCompleted(data.pass);
    });
    $(Khan).bind("hintUsed", function(ev, data) {
        exerciseData.hintUsed = true;
        exerciseData.percentCompleted = 0;
        updateStreakBar();
    });
    $("#next-question-button").click(function() {
        _.defer(function() {
            exerciseData.hintUsed = false;
            $(Exercises).trigger("readyForNextProblem", {userExercise: exerciseData});
        });
    });
});