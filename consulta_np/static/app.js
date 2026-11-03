(function () {
  "use strict";
  var form = document.getElementById("form-consulta");
  if (!form || !window.fetch || !window.FormData) { return; }
  var mensaje = document.getElementById("mensaje");
  var boton = document.getElementById("boton-consultar");

  function mostrar(texto, clase) {
    mensaje.hidden = false;
    mensaje.className = "mensaje " + clase;
    mensaje.textContent = texto;
  }

  function nombreArchivo(cabecera) {
    var m = /filename="([^"]+)"/.exec(cabecera || "");
    return m ? m[1] : "consulta_np.xlsx";
  }

  form.addEventListener("submit", function (evento) {
    evento.preventDefault();
    var archivo = form.archivo.files[0];
    if (!archivo) { mostrar("Seleccione un archivo .xlsx.", "error"); return; }
    if (!/\.xlsx$/i.test(archivo.name)) { mostrar("Solo se aceptan archivos .xlsx.", "error"); return; }
    boton.disabled = true;
    boton.setAttribute("aria-busy", "true");
    mostrar("Procesando " + archivo.name + "... Esto puede tardar varios minutos.", "cargando");

    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    }).then(function (r) {
      if (r.ok) {
        var nombre = nombreArchivo(r.headers.get("Content-Disposition"));
        var total = r.headers.get("X-Total-NP"), enc = r.headers.get("X-Encontrados"), no = r.headers.get("X-No-Encontrados");
        return r.blob().then(function (blob) {
          var url = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = url; a.download = nombre;
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
          mostrar("Listo: " + total + " NP consultados (" + enc + " encontrados, " + no + " no encontrados). Se descargo " + nombre + ".", "ok");
        });
      }
      return r.json().then(function (d) { mostrar(d.error || "Error inesperado.", "error"); },
                           function () { mostrar("Error inesperado (HTTP " + r.status + ").", "error"); });
    }).catch(function () {
      mostrar("No se pudo contactar al servidor. Revise su conexion e intente de nuevo.", "error");
    }).then(function () {
      boton.disabled = false;
      boton.removeAttribute("aria-busy");
    });
  });
})();