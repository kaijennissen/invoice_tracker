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
    Extract invoice data from these images. Be precise with dates (YYYY-MM-DD) and amounts (numeric only, no currency symbols). The total amount (Bruttobetrag) must be extracted with high precision. For multi-page documents, the total is typically on the last page.

    If no explicit due date is given, calculate it from payment terms (e.g. "14 Tage" after issue date).
    Recipient: omit salutations (Herr, Frau, Mr., Mrs., Dr., Prof.).
    Party: use full name, expand abbreviations like MVZ to Medizinisches Versorgungszentrum.

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
