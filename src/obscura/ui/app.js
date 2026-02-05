/* Obscura UI — communicates with Python backend via pywebview JS bridge. */

async function loadProjects() {
    const main = document.getElementById("project-list");
    try {
        const result = await window.pywebview.api.list_projects();
        const projects = JSON.parse(result);
        if (projects.length === 0) {
            main.innerHTML = "<p>No projects yet. Create one to get started.</p>";
            return;
        }
        main.innerHTML = projects.map(p => `
            <div class="project-card" onclick="openProject('${p.name}')">
                <h3>${p.name}</h3>
                <div class="meta">
                    ${p.last_run ? "Last run: " + p.last_run : "Not yet run"}
                    &middot; Language: ${p.language}
                </div>
            </div>
        `).join("");
    } catch (e) {
        main.innerHTML = "<p>Error loading projects.</p>";
    }
}

async function openProject(name) {
    /* Placeholder — will navigate to project workspace screen. */
    console.log("Open project:", name);
}

document.getElementById("new-project-btn").addEventListener("click", async () => {
    const name = prompt("Project name:");
    if (name) {
        await window.pywebview.api.create_project(name);
        loadProjects();
    }
});

/* Initialize when pywebview bridge is ready. */
window.addEventListener("pywebviewready", loadProjects);
