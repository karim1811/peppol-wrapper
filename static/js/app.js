document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("invoiceForm");
  const modal = document.getElementById("resultModal");
  const resultContent = document.getElementById("resultContent");
  const resultTitle = document.getElementById("resultTitle");
  const downloadXmlBtn = document.getElementById("downloadXml");
  const sendInvoiceBtn = document.getElementById("sendInvoice");
  const addLineBtn = document.getElementById("addLine");
  const linesContainer = document.getElementById("linesContainer");

  let lastXml = null;
  let lastInvoiceJson = null;

  document.querySelector(".modal .close").addEventListener("click", () => {
    modal.classList.add("hidden");
  });

  window.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.add("hidden");
    }
  });

  downloadXmlBtn.addEventListener("click", () => {
    if (!lastXml) return;
    const blob = new Blob([lastXml], { type: "application/xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `facture-${document.getElementById("invoice_number").value || "invoice"}.xml`;
    a.click();
    URL.revokeObjectURL(url);
  });

  sendInvoiceBtn.addEventListener("click", async () => {
    if (!lastInvoiceJson) return;
    try {
      const res = await fetch("/invoices/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastInvoiceJson),
      });
      const data = await res.json();
      resultTitle.textContent = "Envoi Peppol";
      resultContent.textContent = JSON.stringify(data, null, 2);
      modal.classList.remove("hidden");
    } catch (err) {
      alert("Erreur lors de l'envoi : " + err.message);
    }
  });

  addLineBtn.addEventListener("click", () => {
    const idx = linesContainer.children.length;
    const div = document.createElement("div");
    div.className = "invoice-line";
    div.innerHTML = `
            <div class="form-row">
                <div class="form-group">
                    <label>Description *</label>
                    <input type="text" name="lines[${idx}][description]" required>
                </div>
                <div class="form-group">
                    <label>Quantité</label>
                    <input type="number" name="lines[${idx}][quantity]" value="1" step="0.01" min="0.01">
                </div>
                <div class="form-group">
                    <label>Prix unitaire HT</label>
                    <input type="number" name="lines[${idx}][unit_price]" step="0.01" min="0" required>
                </div>
                <div class="form-group">
                    <label>TVA (%)</label>
                    <input type="number" name="lines[${idx}][tax_percent]" value="20" step="0.1">
                </div>
            </div>
        `;
    linesContainer.appendChild(div);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    const payload = buildInvoicePayload(formData);
    lastInvoiceJson = payload;
    const action = formData.get("action") || "validate";

    try {
      const url = action === "build" ? "/invoices/build-xml" : "/invoices/validate";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      lastXml = data.xml || data.xml_preview || null;
      resultTitle.textContent = action === "build" ? "XML généré" : "Validation";
      resultContent.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
      modal.classList.remove("hidden");
    } catch (err) {
      alert("Erreur : " + err.message);
    }
  });

  function buildInvoicePayload(formData) {
    const lines = [];
    const lineEls = linesContainer.querySelectorAll(".invoice-line");
    lineEls.forEach((el, idx) => {
      const inputs = el.querySelectorAll("input");
      lines.push({
        description: inputs[0].value,
        quantity: parseFloat(inputs[1].value) || 1,
        unit_price: parseFloat(inputs[2].value) || 0,
        unit_code: "C62",
        tax_category: "S",
        tax_percent: parseFloat(inputs[3].value) || 20,
      });
    });

    return {
      invoice_number: formData.get("invoice_number"),
      issue_date: formData.get("issue_date"),
      due_date: formData.get("due_date") || undefined,
      currency: formData.get("currency") || "EUR",
      buyer_reference: "REF-ACHETEUR",
      seller: {
        name: formData.get("seller_name"),
        endpoint_id: formData.get("seller_endpoint_id"),
        endpoint_scheme: "9915",
        street: formData.get("seller_street"),
        city: formData.get("seller_city"),
        postal_code: formData.get("seller_postal"),
        country_code: (formData.get("seller_country") || "FR").toUpperCase(),
        legal_id: formData.get("seller_legal_id"),
        legal_id_scheme: "0002",
      },
      buyer: {
        name: formData.get("buyer_name"),
        endpoint_id: formData.get("buyer_endpoint_id"),
        endpoint_scheme: "9915",
        street: formData.get("buyer_street"),
        city: formData.get("buyer_city"),
        postal_code: formData.get("buyer_postal"),
        country_code: (formData.get("buyer_country") || "FR").toUpperCase(),
        legal_id: formData.get("buyer_legal_id"),
        legal_id_scheme: "0002",
      },
      lines,
      payment_means_code: "30",
      iban: formData.get("iban") || undefined,
    };
  }
});
