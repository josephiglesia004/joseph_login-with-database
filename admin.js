// Live search sa user table.
var search = document.getElementById("user-search");
if (search) {
  var rows = Array.prototype.slice.call(document.querySelectorAll("tbody tr"));
  var empty = document.getElementById("search-empty");

  search.addEventListener("input", function () {
    var term = search.value.trim().toLowerCase();
    var visible = 0;

    rows.forEach(function (row) {
      var match = (row.dataset.search || "").indexOf(term) !== -1;
      row.hidden = !match;
      if (match) visible += 1;
    });

    if (empty) {
      empty.hidden = visible !== 0;
    }
  });
}
