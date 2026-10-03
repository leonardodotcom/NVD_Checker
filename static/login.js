document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("login-error");
  const button = e.target.querySelector("button");
  error.hidden = true;
  button.disabled = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("username").value,
        password: document.getElementById("password").value,
      }),
    });
    if (res.ok) {
      window.location.href = "/";
      return;
    }
    let detail = "Sign-in failed";
    try { detail = (await res.json()).detail || detail; } catch {}
    error.textContent = detail;
    error.hidden = false;
  } catch {
    error.textContent = "Cannot reach the server";
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});
