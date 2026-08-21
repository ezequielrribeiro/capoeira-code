import { render } from "./render.js";
const axios = require("axios");

function loadDashboard(user) {
    return axios.get("/api/dashboard/" + user);
}

class DashboardController {
    refresh() {
        return render(loadDashboard(this.user));
    }
}

const formatTitle = (title) => {
    return title.toUpperCase();
};
