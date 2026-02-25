// Defining a data model.
class InvoiceData {
  party string
  invoice_id string
  issue_date string @description("ISO 8601 date format e.g., 2023-10-15")
  due_date string @description("ISO 8601 date format e.g., 2023-10-15")
  amount float
  currency string
  recipient string
}

// Create a function to extract invoice data from images.
function ExtractInvoiceData(images: image[]) -> InvoiceData {
  // Specify a client as provider/model-name
  // You can also use custom LLM params with a custom client name from clients.baml like "client CustomGPT5" or "client CustomSonnet4"
  client CustomOllama // Uses local Ollama instance.
  prompt #"
    Extract invoice data from these images.

    Rules:
    - **Dates**: Use YYYY-MM-DD format. The invoice/issue date is always stated explicitly. The due date may NOT be stated directly — if only a payment term is given (e.g. "zahlbar innerhalb von 14 Tagen", "Zahlungsziel: 30 Tage"), calculate the due date by adding that duration to the invoice date.
    - **Amount**: This is the most critical field — extract the total amount with high precision. Use the final/gross total (Bruttobetrag / Gesamtbetrag). Numeric only, no currency symbols.
    - **Recipient**: Extract the invoice recipient (the person or entity being billed). Strip all formal salutations and titles such as Mr., Mrs., Herr, Frau, Dr., Prof. — return only the plain name.
    - **Party**: Extract the issuing party (company/practice name). Use the full standardized name — expand common German abbreviations (e.g. "MVZ" → "Medizinisches Versorgungszentrum", "GmbH" stays "GmbH"). Include the full legal entity name as printed.
    - For multi-page documents, the total amount is typically on the last page.

    {% for img in images %}
    {{ img }}
    {% endfor %}

    {{ ctx.output_format }}
  "#
}



// Test the function with a sample invoice. Open the VSCode playground to run this.
test TestName {
  functions [ExtractInvoiceData]
  args {
    images [{ file "/Users/kjennissen/01_projects/invoice_tracker/invoice.png" }]
  }
}
