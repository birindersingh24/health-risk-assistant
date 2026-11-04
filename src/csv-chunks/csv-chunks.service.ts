import { Injectable } from '@nestjs/common';
import csvParser from 'csv-parser';
import fs from 'fs';
import os from 'os';
import {
  env,
  pipeline,
  FeatureExtractionPipeline,
} from '@huggingface/transformers';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';

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

  async createGuidelinesChunk(): Promise<
    { docId: string; audience: string; diseaseTitle: string; text: string }[]
  > {
    const folderPath = 'mocks/health/data/corpus/notes';
    let results: {
      docId: string;
      audience: string;
      diseaseTitle: string;
      text: string;
    }[] = [];
    try {
      const files = await readdir(folderPath);
      let diseaseTitle = '';
      let docId = '';
      let audience = '';
      for (const file of files) {
        const fullPath = path.join(folderPath, file);
        const rawMarkdown: string[] = fs
          .readFileSync(fullPath, 'utf8')
          .split('\n');
        let rowList: string = '';
        for (const key in rawMarkdown) {
          switch (key) {
            case '1':
              docId = rawMarkdown[key];
              break;
            case '6':
              audience = rawMarkdown[key];
              break;
            case '8':
              diseaseTitle = rawMarkdown[key];
              break;
          }
          rowList += `${key}: ${rawMarkdown[key]}, `;
        }
        results.push({ docId, audience, diseaseTitle, text: rowList });
      }
      return results;
    } catch (error) {
      throw new Error(
        `Error occurred while creating guidelines chunks: ${error}`,
      );
    }
  }

  async createPatientChunk(): Promise<{ patientId: string; text: string }[]> {
    const folderPath = 'mocks/health/data/corpus/notes';
    let results: {
      patientId: string;
      text: string;
    }[] = [];
    try {
      const files = await readdir(folderPath);
      let patientId = '';
      for (const file of files) {
        const fullPath = path.join(folderPath, file);
        const rawMarkdown: string[] = fs
          .readFileSync(fullPath, 'utf8')
          .split('\n');
        let rowList: string = '';
        for (const key in rawMarkdown) {
          switch (key) {
            case '1':
              patientId = rawMarkdown[key];
              break;
          }
          rowList += `${key}: ${rawMarkdown[key]}, `;
        }
        results.push({ patientId, text: rowList });
      }
      return results;
    } catch (error) {
      throw new Error(`Error occurred while creating patient chunks: ${error}`);
    }
  }

  // createChunks(): Promise<
  //   { patientId: string; visitDate: string; text: string }[]
  // > {
  //   try {
  //     return new Promise((resolve, reject) => {
  //       const results: {
  //         patientId: string;
  //         visitDate: string;
  //         text: string;
  //       }[] = [];
  //       fs.createReadStream('mocks/patient_medical_history.csv')
  //         .on('error', reject)
  //         .pipe(csvParser())
  //         .on('error', reject)
  //         .on('data', (row) => {
  //           let rowList: string = '';
  //           for (const key in row) {
  //             rowList += `${key}: ${row[key]}, `;
  //           }
  //           results.push({
  //             patientId: row.PatientId,
  //             visitDate: row.VisitDate,
  //             text: rowList,
  //           });
  //         })
  //         .on('end', () => resolve(results));
  //     });
  //   } catch (error) {
  //     throw new Error(`Error occurred while creating CSV chunks: ${error}`);
  //   }
  // }

  async embeddingChunks(
    chunks: { text: string }[],
    batchSize = 32,
  ): Promise<number[][]> {
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
