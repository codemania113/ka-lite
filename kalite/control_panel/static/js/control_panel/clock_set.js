$(function() {
    $('#time_select').timepicker({
        disableFocus: true,
        showMeridian: false,
        minuteStep: 1
        });
    $('#date_select').datepicker({
        dateFormat: "dd-mm-yy",
        altField: "#standard-date",
        altFormat: "yy-mm-dd"
    });

    $("#date_select").datepicker('setDate', new Date());

    $('#set_time').click(
        function () {
            var data = {
                date_time: $('#standard-date').val() + " " + $('#time_select').val()
            };
            doRequest(TIME_SET_URL, data)
                .success(function(data) {
                    show_api_messages(data, "id_set_time");
                })
                .fail(function(resp) {
                    communicate_api_failure(resp, "id_set_time");
                });
        });
});