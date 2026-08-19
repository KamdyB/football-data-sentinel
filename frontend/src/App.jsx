import { useState } from "react";
import { processBatch } from "./api";
import "./App.css";

function App() {
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function refreshData() {
        setLoading(true);
        setError("");

        try {
            const payload = {
                players: []
            };

            const result = await processBatch(payload);
            setReport(result);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    return (
        <main>
            <header>
                <h1>Sentinel</h1>
                <button onClick={refreshData} disabled={loading}>
                    {loading ? "PROCESSING..." : "REFRESH DATA"}
                </button>
            </header>

            {error && <p>{error}</p>}

            {report && (
                <section>
                    <h2>{report.status.toUpperCase()}</h2>

                    <p>Raw: {report.records.raw}</p>
                    <p>Player rows: {report.records.player_rows}</p>
                    <p>Trusted: {report.records.final_trusted}</p>
                    <p>Recovered: {report.records.recovered}</p>
                    <p>Quarantined: {report.records.quarantined}</p>
                </section>
            )}
        </main>
    );
}

export default App;