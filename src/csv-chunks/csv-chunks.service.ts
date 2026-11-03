import { Injectable } from '@nestjs/common';
import csvParser from 'csv-parser';
import fs from 'fs';
import os from 'os';
import path from 'path';
import {
  env,
  pipeline,
  FeatureExtractionPipeline,
} from '@huggingface/transformers';

// Keep the downloaded model outside node_modules: writes there trigger the
// watch-mode recompiler, which restarts the app mid-download.
env.cacheDir = path.join(os.homedir(), '.cache', 'huggingface');

@Injectable()
export class CsvChunkService {
  private extractorPromise?: Promise<FeatureExtractionPipeline>;

  // Loads the model on first use and reuses it for every later request.
  private getExtractor(): Promise<FeatureExtractionPipeline> {
    this.extractorPromise ??= pipeline(
      'feature-extraction',
      'Xenova/all-MiniLM-L6-v2',
    );
    return this.extractorPromise;
  }

  createChunks(): Promise<{ patientId: string; visitDate: string; text: string }[]> {
    try {
      return new Promise((resolve, reject) => {
        const results: { patientId: string; visitDate: string; text: string }[] = [];
        fs.createReadStream('mocks/patient_medical_history.csv')
          .on('error', reject)
          .pipe(csvParser())
          .on('error', reject)
          .on('data', (row) => {
            let rowList: string = '';
            for (const key in row) {
              rowList += `${key}: ${row[key]}, `;
            }
            results.push({ patientId: row.PatientId, visitDate: row.VisitDate, text: rowList });
          })
          .on('end', () => resolve(results));
      });
    } catch (error) {
      throw new Error(`Error occurred while creating CSV chunks: ${error}`);
    }
  }

  async embeddingChunks(chunks: { text: string }[], batchSize = 32): Promise<number[][]> {
    try {
      const extractor = await this.getExtractor();
      const vectors: number[][] = [];
      for (let i = 0; i < chunks.length; i += batchSize) {
        const batch = chunks.slice(i, i + batchSize).map((chunk) => chunk.text);
        const output = await extractor(batch, {
          pooling: 'mean',
          normalize: true,
        });
        vectors.push(...(output.tolist() as number[][]));
      }
      return vectors;
    } catch (error) {
      throw new Error(`Error occurred while creating CSV chunks: ${error}`);
    }
  }
}
