import { Module } from '@nestjs/common';
import { CsvChunkController } from './csv-chunks.controller.js';
import { CsvChunkService } from './csv-chunks.service.js';
import { GuidelineDBService } from '../VectorService/guidelines-db.js';
import { VisitDBService } from '../VectorService/visit-db.js';

@Module({
  controllers: [CsvChunkController],
  providers: [CsvChunkService, GuidelineDBService, VisitDBService],
})
export class CsvChunksModule {}
