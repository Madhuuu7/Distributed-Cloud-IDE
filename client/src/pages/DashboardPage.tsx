import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { projectsApi } from "../services/api";

type Project = {
  id: number;
  name: string;
  owner_id: number;
};

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectName, setProjectName] = useState("");

  const navigate = useNavigate();
  const loadProjects = async () => {
    try {
      const response = await projectsApi.list();
      setProjects(response.data);
    } catch (error) {
      console.error("Failed to load projects", error);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const createProject = async () => {
    if (!projectName.trim()) return;

    try {
      await projectsApi.create({
        name: projectName,
      });

      setProjectName("");
      loadProjects();
    } catch (error) {
      console.error("Failed to create project", error);
    }
  };

  const deleteProject = async (id: number) => {
    try {
      await projectsApi.delete(id);
      loadProjects();
    } catch (error) {
      console.error("Failed to delete project", error);
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6">
        <h1 className="text-3xl font-bold text-white">
          Distributed Cloud IDE
        </h1>

        <p className="mt-2 text-slate-400">
          Manage your cloud projects.
        </p>

        <div className="mt-6 flex gap-3">
          <input
            className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-white"
            placeholder="Project Name"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
          />

          <button
            onClick={createProject}
            className="rounded-lg bg-blue-600 px-5 py-2 text-white hover:bg-blue-700"
          >
            Create
          </button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {projects.map((project) => (
          <div
            key={project.id}
            className="rounded-2xl border border-slate-800 bg-slate-900 p-5"
          >
            <h2 className="text-xl font-semibold text-white">
              {project.name}
            </h2>

            <p className="mt-2 text-slate-400">
              Owner ID: {project.owner_id}
            </p>

            <div className="mt-5 flex gap-2">
              <button
                onClick={() => navigate(`/ide/${project.id}`)}
                className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          >
                Open IDE
              </button>

              <button
                onClick={() => deleteProject(project.id)}
                className="rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}