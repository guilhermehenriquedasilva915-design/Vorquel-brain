# Source manifest — JustInCache/n8n-workflows

- Source: `JustInCache/n8n-workflows`
- Intended role: raw external corpus / reference examples for n8n patterns
- Trust: `RAW_UNTRUSTED`
- Snapshot observed during initial audit: `5a7864987c22930521382b597873b713cc830dac`
- Automatic execution: forbidden
- Automatic promotion to validated knowledge: forbidden

## Initial security observations

The source contains useful workflow JSON examples, but the initial audit also found privileged patterns including Execute Command, SSH, dynamic code and a workflow exporting decrypted n8n credentials. Source metadata such as `production-ready` is not treated as evidence of safety.
