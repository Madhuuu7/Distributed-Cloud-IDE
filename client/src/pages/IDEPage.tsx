import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import * as monaco from 'monaco-editor';
import { filesApi } from '../services/api';

type FileItem = {
  id: number;
  name: string;
  path: string;
  content: string;
};
export default function IDEPage() {
  const editorRef = useRef<HTMLDivElement | null>(null);

  const { projectId } = useParams();

  const [files, setFiles] = useState<FileItem[]>([]);

  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);

  const editorInstance = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);

  console.log("Project ID:", projectId);

  const loadFiles = async () => {
  if (!projectId) return;

  try {
    const response = await filesApi.list(projectId);
    setFiles(response.data);
  } catch (error) {
    console.error("Failed to load files", error);
  }
};

  const createFile = async () => {
  if (!projectId) return;

  const name = prompt("Enter file name");

  if (!name) return;

  try {
    await filesApi.create(projectId, {
      name,
      content: "",
    });

    loadFiles();
  } catch (error) {
    console.error("Failed to create file", error);
  }
};

  const loadFile = async (file: FileItem) => {
  try {
    const response = await filesApi.get(file.id);

    setSelectedFile(response.data);

    editorInstance.current?.setValue(response.data.content);
  } catch (error) {
    console.error("Failed to load file", error);
  }
};

  const saveFile = async () => {
  if (!selectedFile || !editorInstance.current) return;

  try {
    await filesApi.update(selectedFile.id, {
      content: editorInstance.current.getValue(),
    });

    alert("File saved successfully!");
  } catch (error) {
    console.error("Failed to save file", error);
    alert("Failed to save file.");
  }
};

  useEffect(() => {
    if (!editorRef.current) return;

    const editor = monaco.editor.create(editorRef.current, {
      value: '',
      language: 'javascript',
      theme: 'vs-dark',
      automaticLayout: true
    });

    editorInstance.current = editor;

    loadFiles();

    return () => editor.dispose();
  }, [projectId]);

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <aside className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Explorer</h2>

          <button
            onClick={createFile}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
          >
            + New
          </button>
        </div>
        <ul className="mt-4 space-y-2 text-sm text-slate-400">
          {files.length === 0 ? (
            <li className="rounded px-3 py-2 text-slate-500">
              No files found
            </li>
          ) : (
            files.map((file) => (
              <li
                key={file.id}
                onClick={() => loadFile(file)}
                className="cursor-pointer rounded px-3 py-2 hover:bg-slate-800"
              >
                {file.name}
              </li>
            ))
          )}  
        </ul>
      </aside>

      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80">
        <div className="border-b border-slate-800 px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-white">
                {selectedFile?.name ?? "No file selected"}
              </p>
              <p className="text-xs text-slate-500">
                {selectedFile?.name.endsWith(".py")
                  ? "Python"
                  : selectedFile?.name.endsWith(".js")
                  ? "JavaScript"
                  : "Text"}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={saveFile}
                className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700"
              >
                Save
              </button>

              <button
                className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white"
              >
                Run Code
              </button>
            </div>
          </div>
        </div>
        <div ref={editorRef} className="h-[560px]" />
      </section>
    </div>
  );
}
