
window.onload = function() {
  // Build a system
  var url = window.location.search.match(/url=([^&]+)/);
  if (url && url.length > 1) {
    url = decodeURIComponent(url[1]);
  } else {
    url = window.location.origin;
  }
  var options = {
  "swaggerDoc": {
    "openapi": "3.0.0",
    "info": {
      "title": "Frequency",
      "version": "1.0.0"
    },
    "servers": [
      {
        "url": "https://{server}/api",
        "variables": {
          "server": {
            "enum": [
              "staging-cmp.frequencyads.com",
              "cmp.frequencyads.com"
            ],
            "default": "staging-cmp.frequencyads.com"
          }
        }
      }
    ],
    "tags": [
      {
        "name": "Authorization",
        "description": "Authorization entry point"
      },
      {
        "name": "Application",
        "description": ""
      },
      {
        "name": "Application Draft",
        "description": ""
      },
      {
        "name": "Application Draft Creatives",
        "description": ""
      },
      {
        "name": "Application Data Signals",
        "description": ""
      },
      {
        "name": "Asset Library",
        "description": ""
      },
      {
        "name": "Data Signals",
        "description": ""
      },
      {
        "name": "Internal Campaign",
        "description": "Internal API for campaign management (used by Retool)"
      },
      {
        "name": "Internal Flight",
        "description": "Internal API for flight management (used by Retool)"
      }
    ],
    "paths": {
      "/campaign/validate/{client}/{token}": {
        "get": {
          "tags": [
            "Authorization"
          ],
          "summary": "Get Application details on the basis of provided token",
          "description": "",
          "operationId": "token",
          "parameters": [
            {
              "name": "client",
              "in": "path",
              "description": "client Name",
              "required": true,
              "schema": {
                "type": "string",
                "example": "triton"
              }
            },
            {
              "name": "token",
              "in": "path",
              "description": "Token",
              "required": true,
              "schema": {
                "type": "string",
                "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOjEsInRlbmFudF9uYW1lIjoiRiMgVGVzdGluZyIsInVzZXJfZW1haWwiOiJpbmFtQGZzaGFycC5jbyIsImFkdmVydGlzZXJfaWQiOjEsImFkdmVydGlzZXJfbmFtZSI6IktGQyIsImNhbXBhaWduX2lkIjoxMDE2LCJjYW1wYWlnbl9uYW1lIjoiaGVsbG8gMTAxNiIsImZsaWdodF9pZCI6MTM1LCJjbV91bml0X2lkIjoxMzQzMywiZmxpZ2h0X25hbWUiOiJUZXN0IDEzNSIsImNyZWF0aXZlX3R5cGUiOiJzdGFuZGFyZCIsImNyZWF0aXZlX2R1cmF0aW9uIjoiMTUiLCJpYXQiOjE2MTM0NTUzMjN9.LTmyaChMw2Xy4T-va5EYiEUik53VrA8IwVnc30TN_EI"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          }
        }
      },
      "/application/duplicate/{client}/{token}": {
        "get": {
          "tags": [
            "Authorization"
          ],
          "summary": "Duplicate Application Via Token",
          "description": "",
          "operationId": "duplicateViaToken",
          "parameters": [
            {
              "name": "client",
              "in": "path",
              "description": "client Name",
              "required": true,
              "schema": {
                "type": "string",
                "example": "triton"
              }
            },
            {
              "name": "token",
              "in": "path",
              "description": "Token",
              "required": true,
              "schema": {
                "type": "string",
                "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOjEsInRlbmFudF9uYW1lIjoiRiMgVGVzdGluZyIsInVzZXJfZW1haWwiOiJpbmFtQGZzaGFycC5jbyIsImFkdmVydGlzZXJfaWQiOjEsImFkdmVydGlzZXJfbmFtZSI6IktGQyIsImNhbXBhaWduX2lkIjoxMDE2LCJjYW1wYWlnbl9uYW1lIjoiaGVsbG8gMTAxNiIsImZsaWdodF9pZCI6MTM1LCJjbV91bml0X2lkIjoxMzQzMywiZmxpZ2h0X25hbWUiOiJUZXN0IDEzNSIsImNyZWF0aXZlX3R5cGUiOiJzdGFuZGFyZCIsImNyZWF0aXZlX2R1cmF0aW9uIjoiMTUiLCJpYXQiOjE2MTM0NTUzMjN9.LTmyaChMw2Xy4T-va5EYiEUik53VrA8IwVnc30TN_EI"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          }
        }
      },
      "/application/duplicate-multiple/{client}/{token}": {
        "get": {
          "tags": [
            "Authorization"
          ],
          "summary": "Duplicate Multiple Application Via Token",
          "description": "",
          "operationId": "duplicateMultipleViaToken",
          "parameters": [
            {
              "name": "client",
              "in": "path",
              "description": "client Name",
              "required": true,
              "schema": {
                "type": "string",
                "example": "triton"
              }
            },
            {
              "name": "token",
              "in": "path",
              "description": "Token",
              "required": true,
              "schema": {
                "type": "string",
                "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhZFVuaXRzIjpbeyJzb3VyY2UiOnsiY21fdW5pdF9pZCI6OTM1fSwiZGVzdGluYXRpb24iOnsidGVuYW50X2lkIjoxLCJ0ZW5hbnRfbmFtZSI6IkYjIiwidXNlcl9lbWFpbCI6Im1hdHRAZWZzaGFycC5jb20iLCJhZHZlcnRpc2VyX2lkIjo5ODk5LCJhZHZlcnRpc2VyX25hbWUiOiJBZHZlcnRpc2VyICMxOSAoRnJvbSBGcmVxdWVuY3kpIiwiY2FtcGFpZ25faWQiOjEyMzQ1LCJjYW1wYWlnbl9uYW1lIjoiMTIzNDUtQ2FtcGFpZ24gIzQgKEZyb20gRnJlcXVlbmN5KSIsImZsaWdodF9pZCI6MTMwMywiZmxpZ2h0X25hbWUiOiJUZXN0IDEzMDMifX0seyJzb3VyY2UiOnsiY21fdW5pdF9pZCI6OTQwfSwiZGVzdGluYXRpb24iOnsidGVuYW50X2lkIjoxLCJ0ZW5hbnRfbmFtZSI6IkYjIiwidXNlcl9lbWFpbCI6Im1hdHRAZWZzaGFycC5jb20iLCJhZHZlcnRpc2VyX2lkIjo5ODk5LCJhZHZlcnRpc2VyX25hbWUiOiJBZHZlcnRpc2VyICMxOSAoRnJvbSBGcmVxdWVuY3kpIiwiY2FtcGFpZ25faWQiOjEyMzQ0LCJjYW1wYWlnbl9uYW1lIjoiMTIzNDQtQ2FtcGFpZ24gIzQgKEZyb20gRnJlcXVlbmN5KSIsImZsaWdodF9pZCI6MTMwNCwiZmxpZ2h0X25hbWUiOiJUZXN0IDEzMDQifX1dLCJpYXQiOjE2NDgxMTMwNjR9.6X4KvplHVjaq0IQRNtvxNpW0pTdHpDSpyP7FSUSmEcY"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          }
        }
      },
      "/application/{appId}/creative-creative-settings": {
        "post": {
          "tags": [
            "Application"
          ],
          "summary": "Set Application Creative Settings",
          "description": "",
          "operationId": "addCreativeSettings",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/creativeSettings"
                }
              }
            }
          },
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "string"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/creative-duration": {
        "post": {
          "tags": [
            "Application"
          ],
          "summary": "Set Application Creative Duration",
          "description": "",
          "operationId": "addCreativeDuration",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/creativeDuration"
                }
              }
            }
          },
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "string"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft": {
        "post": {
          "tags": [
            "Application Draft"
          ],
          "summary": "Create Empty Draft in application",
          "description": "",
          "operationId": "create-empty-draft",
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}/update-audio-type": {
        "put": {
          "tags": [
            "Application Draft"
          ],
          "summary": "Update application audio type (Standard/Dynamic)",
          "description": "",
          "operationId": "update-audio-type",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "type": {
                      "type": "string",
                      "enum": [
                        "dynamic_audio_builder",
                        "standard_audio_builder"
                      ],
                      "example": "dynamic_audio_builder"
                    }
                  }
                }
              }
            }
          },
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}/publish": {
        "post": {
          "tags": [
            "Application Draft"
          ],
          "summary": "Publish Application draft",
          "description": "",
          "operationId": "publishe",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "schedulePublishDate": {
                      "type": "string",
                      "example": "22/03/2021 "
                    }
                  }
                }
              }
            }
          },
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}/duplicate": {
        "put": {
          "tags": [
            "Application Draft"
          ],
          "summary": "Duplicate a draft in application",
          "description": "",
          "operationId": "duplicate-draft",
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}": {
        "delete": {
          "tags": [
            "Application Draft"
          ],
          "summary": "Delete a draft in application",
          "description": "",
          "operationId": "delete-draft",
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}/creatives": {
        "get": {
          "tags": [
            "Application Draft Creatives"
          ],
          "summary": "Get application draft creatives",
          "description": "",
          "operationId": "creatives",
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}/creative": {
        "post": {
          "tags": [
            "Application Draft Creatives"
          ],
          "summary": "Add a creative to application draft",
          "description": "",
          "operationId": "add-creative",
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "required": [
                    "fileName",
                    "fileUrl",
                    "type",
                    "serveOption"
                  ],
                  "properties": {
                    "fileName": {
                      "type": "string"
                    },
                    "fileUrl": {
                      "type": "string"
                    },
                    "type": {
                      "type": "string",
                      "enum": [
                        "audio",
                        "video",
                        "image",
                        "placeholder"
                      ]
                    },
                    "serveOption": {
                      "type": "string",
                      "enum": [
                        "random",
                        "sequential"
                      ]
                    },
                    "fileWeight": {
                      "type": "integer",
                      "minimum": 1
                    },
                    "rowIndex": {
                      "type": "integer"
                    },
                    "banners": {
                      "type": "array",
                      "items": {
                        "type": "object"
                      }
                    },
                    "audioProps": {
                      "type": "object"
                    },
                    "videoProps": {
                      "type": "object"
                    },
                    "scriptTags": {
                      "type": "array",
                      "items": {
                        "type": "object"
                      }
                    },
                    "htmlResources": {
                      "type": "array",
                      "items": {
                        "type": "object"
                      }
                    },
                    "iframeResources": {
                      "type": "array",
                      "items": {
                        "type": "object"
                      }
                    },
                    "dataSignals": {
                      "type": "array",
                      "items": {
                        "type": "object"
                      }
                    }
                  }
                }
              }
            }
          },
          "responses": {
            "200": {
              "description": "Creative added successfully"
            },
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}/creatives/[{ids}]": {
        "put": {
          "tags": [
            "Application Draft Creatives"
          ],
          "summary": "Update application draft creatives data",
          "description": "",
          "operationId": "update-creatives",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/creativeOptions"
                }
              }
            }
          },
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "ids",
              "in": "path",
              "description": "Selected Ids",
              "required": true,
              "schema": {
                "type": "array",
                "items": {
                  "type": "integer"
                }
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        },
        "delete": {
          "tags": [
            "Application Draft Creatives"
          ],
          "summary": "Delete creatives",
          "description": "",
          "operationId": "delete-creatives",
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "ids",
              "in": "path",
              "description": "Selected Ids",
              "required": true,
              "schema": {
                "type": "array",
                "items": {
                  "type": "integer"
                }
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/application/{appId}/draft/{draftId}/dynamic-audio-signals/draft/all": {
        "get": {
          "tags": [
            "Application Data Signals"
          ],
          "summary": "Get already defined signals to application draft",
          "description": "",
          "operationId": "all",
          "parameters": [
            {
              "name": "appId",
              "in": "path",
              "description": "Application Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            },
            {
              "name": "draftId",
              "in": "path",
              "description": "Draft Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/dynamic-audio-signals/signal/add": {
        "post": {
          "tags": [
            "Application Data Signals"
          ],
          "summary": "Save Defined Signals to application draft",
          "description": "",
          "operationId": "add",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/saveSignals"
                }
              }
            }
          },
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/assetlibrary/file": {
        "get": {
          "tags": [
            "Asset Library"
          ],
          "summary": "Get creatives as part of Asset Library",
          "description": "",
          "operationId": "filterObject-image",
          "parameters": [
            {
              "name": "campaignId",
              "in": "query",
              "description": "Campaign Id",
              "required": true,
              "schema": {
                "type": "integer",
                "example": 123
              }
            },
            {
              "in": "query",
              "name": "fileType",
              "description": "",
              "required": true,
              "schema": {
                "type": "object",
                "properties": {
                  "fileType": {
                    "type": "array",
                    "items": {
                      "type": "string",
                      "example": "image"
                    }
                  }
                }
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/campaign/{campId}/upload-creative": {
        "post": {
          "tags": [
            "Asset Library"
          ],
          "summary": "Upload creative to Asset Library",
          "description": "",
          "operationId": "upload-creative",
          "requestBody": {
            "required": true,
            "content": {
              "multipart/form-data": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "file": {
                      "type": "string",
                      "format": "binary"
                    },
                    "duration": {
                      "type": "integer"
                    },
                    "applicationId": {
                      "type": "integer"
                    }
                  },
                  "required": [
                    "file",
                    "duration"
                  ]
                }
              }
            }
          },
          "parameters": [
            {
              "name": "campId",
              "in": "path",
              "description": "Campaign Id",
              "required": true,
              "schema": {
                "type": "integer"
              }
            }
          ],
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/dynamic-audio-signals/signals": {
        "get": {
          "tags": [
            "Data Signals"
          ],
          "summary": "Get available Data Signals against tenant",
          "description": "",
          "operationId": "signals",
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/external-metric-report-request": {
        "post": {
          "tags": [
            "Metric Report"
          ],
          "summary": "Metric Report Request",
          "description": "",
          "operationId": "addMetric",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "client": {
                      "type": "string",
                      "example": "triton"
                    },
                    "token": {
                      "type": "string",
                      "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOjEsInRlbmFudF9uYW1lIjoiRiMgVGVzdGluZyIsInVzZXJfZW1haWwiOiJpbmFtQGZzaGFycC5jbyIsImFkdmVydGlzZXJfaWQiOjEsImFkdmVydGlzZXJfbmFtZSI6IktGQyIsImNhbXBhaWduX2lkIjoxMDE2LCJjYW1wYWlnbl9uYW1lIjoiaGVsbG8gMTAxNiIsImZsaWdodF9pZCI6MTM1LCJjbV91bml0X2lkIjoxMzQzMywiZmxpZ2h0X25hbWUiOiJUZXN0IDEzNSIsImNyZWF0aXZlX3R5cGUiOiJzdGFuZGFyZCIsImNyZWF0aXZlX2R1cmF0aW9uIjoiMTUiLCJpYXQiOjE2MTM0NTUzMjN9.LTmyaChMw2Xy4T-va5EYiEUik53VrA8IwVnc30TN_EI"
                    }
                  },
                  "required": [
                    "client",
                    "token"
                  ]
                }
              }
            }
          },
          "responses": {
            "405": {
              "description": "Invalid input"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/internal/campaign": {
        "post": {
          "tags": [
            "Internal Campaign"
          ],
          "summary": "Create a campaign",
          "operationId": "createInternalCampaign",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "required": [
                    "brandId",
                    "name"
                  ],
                  "properties": {
                    "brandId": {
                      "type": "integer",
                      "minimum": 1,
                      "description": "Brand ID to associate the campaign with"
                    },
                    "name": {
                      "type": "string",
                      "description": "Campaign name"
                    },
                    "description": {
                      "type": "string",
                      "nullable": true,
                      "description": "Campaign description"
                    },
                    "targetImpressions": {
                      "type": "integer",
                      "minimum": 0,
                      "nullable": true,
                      "description": "Target number of impressions for the campaign"
                    },
                    "data": {
                      "type": "object",
                      "description": "Additional campaign data"
                    },
                    "tenantId": {
                      "type": "integer",
                      "minimum": 1,
                      "description": "Tenant ID (optional, derived from brand if not provided)"
                    }
                  }
                }
              }
            }
          },
          "responses": {
            "200": {
              "description": "Campaign created successfully"
            },
            "400": {
              "description": "Validation error (e.g. negative targetImpressions, missing required fields)"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/internal/campaign/{id}": {
        "post": {
          "tags": [
            "Internal Campaign"
          ],
          "summary": "Update a campaign",
          "operationId": "updateInternalCampaign",
          "parameters": [
            {
              "name": "id",
              "in": "path",
              "required": true,
              "schema": {
                "type": "integer",
                "minimum": 1
              },
              "description": "Campaign ID"
            }
          ],
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "name": {
                      "type": "string",
                      "description": "Campaign name"
                    },
                    "description": {
                      "type": "string",
                      "nullable": true,
                      "description": "Campaign description"
                    },
                    "targetImpressions": {
                      "type": "integer",
                      "minimum": 0,
                      "nullable": true,
                      "description": "Target number of impressions for the campaign"
                    },
                    "data": {
                      "type": "object",
                      "description": "Additional campaign data"
                    }
                  }
                }
              }
            }
          },
          "responses": {
            "200": {
              "description": "Campaign updated successfully"
            },
            "400": {
              "description": "Validation error"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        },
        "get": {
          "tags": [
            "Internal Campaign"
          ],
          "summary": "Get a campaign by ID",
          "operationId": "getInternalCampaign",
          "parameters": [
            {
              "name": "id",
              "in": "path",
              "required": true,
              "schema": {
                "type": "integer",
                "minimum": 1
              },
              "description": "Campaign ID"
            }
          ],
          "responses": {
            "200": {
              "description": "Campaign details including targetImpressions (integer or null)"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/internal/flight": {
        "post": {
          "tags": [
            "Internal Flight"
          ],
          "summary": "Create a flight",
          "operationId": "createInternalFlight",
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "required": [
                    "campaignId",
                    "name"
                  ],
                  "properties": {
                    "campaignId": {
                      "type": "integer",
                      "minimum": 1,
                      "description": "Parent campaign ID"
                    },
                    "name": {
                      "type": "string",
                      "description": "Flight name"
                    },
                    "targetImpressions": {
                      "type": "integer",
                      "minimum": 0,
                      "nullable": true,
                      "description": "Target number of impressions for the flight"
                    },
                    "startDate": {
                      "type": "string",
                      "format": "date",
                      "description": "Flight start date"
                    },
                    "endDate": {
                      "type": "string",
                      "format": "date",
                      "description": "Flight end date"
                    },
                    "duration": {
                      "type": "integer",
                      "minimum": 0,
                      "description": "Flight duration in seconds"
                    },
                    "description": {
                      "type": "string",
                      "nullable": true,
                      "description": "Flight description"
                    },
                    "adPlacements": {
                      "type": "array",
                      "items": {
                        "type": "string"
                      },
                      "description": "Ad placement types"
                    },
                    "flightAdType": {
                      "type": "string",
                      "description": "Ad read type"
                    }
                  }
                }
              }
            }
          },
          "responses": {
            "200": {
              "description": "Flight created successfully"
            },
            "400": {
              "description": "Validation error (e.g. negative targetImpressions, missing required fields)"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      },
      "/internal/flight/{id}": {
        "post": {
          "tags": [
            "Internal Flight"
          ],
          "summary": "Update a flight",
          "operationId": "updateInternalFlight",
          "parameters": [
            {
              "name": "id",
              "in": "path",
              "required": true,
              "schema": {
                "type": "integer",
                "minimum": 1
              },
              "description": "Flight ID"
            }
          ],
          "requestBody": {
            "required": true,
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "name": {
                      "type": "string",
                      "description": "Flight name"
                    },
                    "targetImpressions": {
                      "type": "integer",
                      "minimum": 0,
                      "nullable": true,
                      "description": "Target number of impressions for the flight"
                    },
                    "startDate": {
                      "type": "string",
                      "format": "date",
                      "description": "Flight start date"
                    },
                    "endDate": {
                      "type": "string",
                      "format": "date",
                      "description": "Flight end date"
                    },
                    "duration": {
                      "type": "integer",
                      "minimum": 0,
                      "description": "Flight duration in seconds"
                    },
                    "description": {
                      "type": "string",
                      "nullable": true,
                      "description": "Flight description"
                    }
                  }
                }
              }
            }
          },
          "responses": {
            "200": {
              "description": "Flight updated successfully"
            },
            "400": {
              "description": "Validation error"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        },
        "get": {
          "tags": [
            "Internal Flight"
          ],
          "summary": "Get a flight by ID",
          "operationId": "getInternalFlight",
          "parameters": [
            {
              "name": "id",
              "in": "path",
              "required": true,
              "schema": {
                "type": "integer",
                "minimum": 1
              },
              "description": "Flight ID"
            }
          ],
          "responses": {
            "200": {
              "description": "Flight details including targetImpressions (integer or null)"
            }
          },
          "security": [
            {
              "bearerAuth": []
            }
          ]
        }
      }
    },
    "components": {
      "schemas": {
        "creativeOptions": {
          "type": "object",
          "properties": {
            "ids": {
              "type": "array",
              "items": {
                "type": "integer"
              },
              "description": "Selected ID."
            },
            "serveOptions": {
              "type": "string"
            },
            "fileIndex": {
              "type": "integer"
            },
            "fileWeight": {
              "type": "integer"
            },
            "banners": {
              "$ref": "#/components/schemas/banners"
            },
            "audioProps": {
              "$ref": "#/components/schemas/audioProps"
            },
            "scriptTags": {
              "$ref": "#/components/schemas/otherResource"
            },
            "htmlResources": {
              "$ref": "#/components/schemas/otherResource"
            },
            "iframeResources": {
              "$ref": "#/components/schemas/otherResource"
            },
            "dataSignals": {
              "$ref": "#/components/schemas/dataSignals"
            }
          },
          "required": [
            "id"
          ]
        },
        "banners": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "example": "rsource File",
                "description": "name."
              },
              "width": {
                "type": "integer",
                "example": 500
              },
              "height": {
                "type": "integer",
                "example": 500
              },
              "clickOut": {
                "type": "string",
                "example": "google.com"
              },
              "altText": {
                "type": "string",
                "example": "alt text"
              },
              "fileUrl": {
                "type": "string",
                "example": "https://f3cdn.s3.amazonaws.com/frequency/staging/image-uploads/designer/1625221349116-Screenshot 2021-06-28 at 3.18.02 PM.png"
              },
              "impressionPixel": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            },
            "required": [
              "name",
              "height",
              "width",
              "clickout",
              "fileUrl"
            ]
          }
        },
        "otherResource": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "example": "rsource File",
                "description": "name."
              },
              "width": {
                "type": "integer",
                "example": 500
              },
              "height": {
                "type": "integer",
                "example": 500
              },
              "clickOut": {
                "type": "string",
                "example": "google.com"
              },
              "altText": {
                "type": "string",
                "example": "alt text"
              },
              "impressionPixel": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            },
            "required": [
              "name",
              "height",
              "width"
            ]
          }
        },
        "audioProps": {
          "type": "object",
          "properties": {
            "start": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "complete": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "midpoint": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "firstQuartile": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "thirdQuartile": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "impressionPixel": {
              "type": "array",
              "items": {
                "type": "string"
              }
            }
          }
        },
        "saveSignals": {
          "type": "object",
          "properties": {
            "applicationDraftId": {
              "type": "integer",
              "description": "The user ID.",
              "example": 123
            },
            "applicationId": {
              "type": "integer",
              "example": 123
            },
            "campaignId": {
              "type": "integer",
              "example": 123
            },
            "dataSignals": {
              "$ref": "#/components/schemas/dataSignals"
            }
          },
          "required": [
            "applicationDraftId",
            "applicationId",
            "dataSignals"
          ]
        },
        "dataSignals": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "example": "name of signal"
              },
              "value": {
                "type": "string",
                "example": "value of signal"
              },
              "type": {
                "type": "string",
                "example": "type of signal"
              },
              "subSignals": {
                "$ref": "#/components/schemas/subSignals"
              }
            },
            "required": [
              "name",
              "value",
              "type",
              "subSignals"
            ]
          }
        },
        "subSignals": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string",
                "example": "name of subsignal"
              },
              "value": {
                "type": "string",
                "example": "value of subsignal"
              }
            },
            "required": [
              "name",
              "value"
            ]
          }
        },
        "creativeDuration": {
          "type": "object",
          "properties": {
            "duration": {
              "type": "integer",
              "format": "int64"
            }
          },
          "example": {
            "duration": 15
          }
        },
        "creativeSettings": {
          "type": "object",
          "properties": {
            "type": {
              "type": "intstringeger",
              "example": "type of creative audio/video"
            },
            "duration": {
              "type": "integer",
              "format": "int64"
            },
            "approvers": {
              "type": "object",
              "format": "int64"
            }
          },
          "example": {
            "type": "audio",
            "duration": 15
          }
        }
      },
      "securitySchemes": {
        "bearerAuth": {
          "type": "apiKey",
          "name": "Authorization",
          "in": "header"
        }
      }
    }
  },
  "customOptions": {}
};
  url = options.swaggerUrl || url
  var urls = options.swaggerUrls
  var customOptions = options.customOptions
  var spec1 = options.swaggerDoc
  var swaggerOptions = {
    spec: spec1,
    url: url,
    urls: urls,
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIStandalonePreset
    ],
    plugins: [
      SwaggerUIBundle.plugins.DownloadUrl
    ],
    layout: "StandaloneLayout"
  }
  for (var attrname in customOptions) {
    swaggerOptions[attrname] = customOptions[attrname];
  }
  var ui = SwaggerUIBundle(swaggerOptions)

  if (customOptions.oauth) {
    ui.initOAuth(customOptions.oauth)
  }

  if (customOptions.authAction) {
    ui.authActions.authorize(customOptions.authAction)
  }

  window.ui = ui
}
