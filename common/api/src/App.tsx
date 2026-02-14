import React, { useEffect } from 'react';

import SwaggerUI from 'swagger-ui';

import spec from './spec.json';

import 'swagger-ui/dist/swagger-ui.css';

function App() {
  useEffect(() => {
    SwaggerUI({
      spec,
      dom_id: '#swaggerRoot',
      defaultModelRendering: 'model',
      filter: true,
      defaultModelsExpandDepth: 2,
      deepLinking: true,
    });
  }, []);

  return <div id="swaggerRoot" />;
}

export default App;
